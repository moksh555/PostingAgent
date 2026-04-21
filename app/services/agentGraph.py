from datetime import datetime
from langgraph.graph import StateGraph, MessagesState, START, END #type: ignore
from langchain_google_genai import ChatGoogleGenerativeAI #type:ignore
from configurations.config import config
from typing_extensions import TypedDict, Annotated #type:ignore
from app.models.AgentModels import AgentRunRequest
from langgraph.checkpoint.memory import InMemorySaver #type: ignore
from langgraph.types import interrupt, Command # type: ignore
from app.prompts.detailedDescription import MARKETING_BRIEF_PROMPT
from app.prompts.postGenerationPrompt import POST_GENERATION_PROMPT
import uuid 
from langchain_core.prompts import ChatPromptTemplate #type:ignore
from langgraph.errors import GraphInterrupt # type:ignore

from app.errorsHandler import (
    NoPayloadError, 
    NoURLError, 
    NoNumberOfPostsError, 
    NoStartDateError, 
    FailedToBuildMarketingBriefError,
    FailedToBuildPosts
)
from app.models.AgentModels import (
    AgentSummary, 
    LLMPostGeneration, 
    AgentPost,
    AgentPostGenerationInterrupt
)
import requests #type:ignore
from bs4 import BeautifulSoup #type:ignore
from pathlib import Path
current_dir = Path(__file__).parent.absolute()

LLM = ChatGoogleGenerativeAI(model="gemini-3-flash-preview", google_api_key=config.GEMINI_API_KEY)
structuredSummaryLLM = LLM.with_structured_output(AgentSummary)

PostGenerationLLM = ChatGoogleGenerativeAI(model="gemini-3-flash-preview", google_api_key=config.GEMINI_API_KEY)
structuredPostGenerationLLM = PostGenerationLLM.with_structured_output(LLMPostGeneration)

def writeSummaryToFile(response: AgentSummary) -> Path:
    # TODO: Write to S3 and get the URL for the file to be used in the next node for generating posts based on the content of the file
    filePath = Path(__file__).parent.parent.parent.absolute() / "testSummary" / response.fileName
    with open(filePath, "w", encoding="utf-8") as f:
        f.write(response.marketingBrief)
    return filePath

class AgentState(TypedDict):
    payload: AgentRunRequest
    marketingNotes: str
    posts: list[AgentPost]

def receiverNode(state: AgentState):
    print("Receiver Node")
    payload = state.get("payload")
    if payload is None:
        raise NoPayloadError("No payload found during Agentic RAG Flow")
    if payload.url is None:
        raise NoURLError("No URL found during Agentic RAG Flow")
    elif payload.numberOfPosts is None:
        raise NoNumberOfPostsError("No number of posts found during Agentic RAG Flow")
    elif payload.startDate is None:
        raise NoStartDateError("No start date found during Agentic RAG Flow")
    return {"payload": payload}

def buildingMarketingBrief(state: AgentState):
    print("Building Marketing Brief Node")
    payload = state.get("payload")

    prompt = MARKETING_BRIEF_PROMPT.format(
        url=payload.url,
        number_of_posts=payload.numberOfPosts,
    )

    try:
        response = structuredSummaryLLM.invoke(prompt)

        if response.marketingBrief is None or response.marketingBrief == "" or response.fileName is None or response.fileName == "":
            raise FailedToBuildMarketingBriefError("Response from model is invalid")
        writeSummaryToFile(response)
        return {"marketingNotes": response.marketingBrief}
    except Exception as e:
        raise FailedToBuildMarketingBriefError(f"Failed to build marketing brief: {e}")

def generatingMarketingPosts(state: AgentState):
    print("Generating Marketing Posts Node")
    marketingNotes = state.get("marketingNotes")
    payload = state.get("payload")
    numberOfPosts = payload.numberOfPosts
    startDate = state.get("payload").startDate
    postList = []
    postNumber = 1
    try:
        for post in range(numberOfPosts):
            postGenerateSystemPrompt = POST_GENERATION_PROMPT
            prompt = ChatPromptTemplate.from_messages([
                ("system", "{system_instruction}"),
                ("human", "{user_input}"),
            ])

            chain = prompt | structuredPostGenerationLLM

            postGenerated = chain.invoke({
                "system_instruction": postGenerateSystemPrompt,
                "user_input": f"Here is the input 'Marketing Note': {marketingNotes}, 'numberOfPosts': {numberOfPosts}, 'startDate': {startDate}, 'platform': 'LinkedIn', 'url': {payload.url}" ,
            })

            # TODO: Create a self loop node to handle case where the response is invalid and make I can set the max try to 3 before raising the error, for now temporarily raising the error
            if postGenerated.content is None or postGenerated.content == "" or postGenerated.publishDate is None or postGenerated.publishDate == "":
                raise FailedToBuildPosts("Response from model is invalid")

            
            answer : AgentPostGenerationInterrupt = interrupt({
                "postContent": postGenerated.content,
                "publishDate": postGenerated.publishDate,
                "actions": ["Accept", "Reject", "Regenerate"],
            })

            if answer.actions == "Accept":
                postList.append(AgentPost(
                    content=postGenerated.content,
                    publishDate=postGenerated.publishDate,
                    platform="LinkedIn",
                    postNumber=postNumber,
                ))
                postNumber += 1
            elif answer.actions == "Reject":
                continue
            elif answer.actions == "Regenerate":
                continue
            print(postList)
        return {"posts": postList}
    except GraphInterrupt:
        raise
    except Exception as e:
        raise FailedToBuildPosts(f"Failed to build posts: {e}")

graph = StateGraph(AgentState)

graph.add_node("receiver", receiverNode)
graph.add_node("buildingMarketingBrief", buildingMarketingBrief)
graph.add_node("generatingMarketingPosts", generatingMarketingPosts)


graph.add_edge(START, "receiver")
graph.add_edge("receiver", "buildingMarketingBrief")
graph.add_edge("buildingMarketingBrief", "generatingMarketingPosts")
graph.add_edge("generatingMarketingPosts", END)
checkpointer = InMemorySaver()
graph = graph.compile(checkpointer=checkpointer) 

if __name__ == "__main__":
    config = {"configurable": {"thread_id": uuid.uuid4()}}
    result = graph.invoke({"payload": AgentRunRequest(url="https://code.claude.com/docs/en/agent-sdk/overview", numberOfPosts=1, startDate=datetime.now())}, config=config, version="v2")


    print(result.interrupts)

    answer = AgentPostGenerationInterrupt(actions="Accept")
    graph.invoke(Command(resume=answer), config=config, version="v2")
