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

# TODO: Later on will have model selection for the user so we can use the best model for the task
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
    regeneratePost: bool
    postRegenerationDescription: str
    postToRegenerate: LLMPostGeneration

def receiverNode(state: AgentState):
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
                return {"regeneratePost": True, "postRegenerationDescription": answer.postChangeDescription, "postToRegenerate": postGenerated}
            print(postList)
        return {"posts": postList}
    except GraphInterrupt:
        raise
    except Exception as e:
        raise FailedToBuildPosts(f"Failed to build posts: {e}")

def regenratePost(state: AgentState):
    postToRegenerate = state.get("postToRegenerate")
    postRegenerationDescription = state.get("postRegenerationDescription")
    postGenerateSystemPrompt = POST_GENERATION_PROMPT
    postsList = state.get("posts")
    prompt = ChatPromptTemplate.from_messages([
        ("system", "{system_instruction}"),
        ("human", "{user_input}"),
    ])
    chain = prompt | structuredPostGenerationLLM
    postReGenerated = chain.invoke({
        "system_instruction": postGenerateSystemPrompt,
        "user_input": f"Here is the input 'Marketing Note': {postToRegenerate.content}, 'postRegenerationDescription': {postRegenerationDescription}" ,
    })
    if postReGenerated.actions == "Regenerate":
        return {"regeneratePost": True, "postRegenerationDescription": answer.postChangeDescription, "postToRegenerate": postReGenerated}
    elif postReGenerated.actions == "Accept":
        postsList.append(AgentPost(
            content=postReGenerated.content,
            publishDate=postReGenerated.publishDate,
            platform="LinkedIn",
            postNumber=len(postsList) + 1,
        ))
        return {"posts": postsList, "regeneratePost": False, "postRegenerationDescription": "", "postToRegenerate": None}
    elif postReGenerated.actions == "Reject":
        return {"regeneratePost": False, "postRegenerationDescription": "", "postToRegenerate": None}

graph = StateGraph(AgentState)

graph.add_node("Validating_Payload", receiverNode)
graph.add_node("Building_Marketing_Brief", buildingMarketingBrief)
graph.add_node("Drafting_And_Reviewing_Posts", generatingMarketingPosts)
graph.add_node("Regenerating_With_Feedback", regenratePost)

def routingGneratePostsNode(state: AgentState):
    if state.get("regeneratePost"):
        return "Regenerating_With_Feedback"
    else:
        return END

def routingRegeneratePostNode(state: AgentState):
    if state.get("regeneratePost"):
        return "Regenerating_With_Feedback"
    else:
        return "Drafting_And_Reviewing_Posts"

graph.add_edge(START, "Validating_Payload")
graph.add_edge("Validating_Payload", "Building_Marketing_Brief")
graph.add_edge("Building_Marketing_Brief", "Drafting_And_Reviewing_Posts")
graph.add_conditional_edges(
    "Drafting_And_Reviewing_Posts", 
    routingGneratePostsNode,
    {
        "Regenerating_With_Feedback": "Regenerating_With_Feedback",
        END: END,
    }
    )

graph.add_conditional_edges(
    "Regenerating_With_Feedback",
    routingRegeneratePostNode,
    {
        "Regenerating_With_Feedback": "Regenerating_With_Feedback",
        "Drafting_And_Reviewing_Posts": "Drafting_And_Reviewing_Posts",
    }
)

checkpointer = InMemorySaver()
graph = graph.compile(checkpointer=checkpointer) 


if __name__ == "__main__":
    config = {"configurable": {"thread_id": uuid.uuid4()}}
    for chunk in graph.stream(
        {"payload": AgentRunRequest(url="https://code.claude.com/docs/en/agent-sdk/overview", numberOfPosts=1, startDate=datetime.now())}, 
        config=config, 
        version="v2"):
        if chunk["type"] == "updates":
            for node_name, state in chunk["data"].items():
                print(f"Node {node_name}")
                if node_name == "__interrupt__":
                    answer = AgentPostGenerationInterrupt(actions="Accept")
                    graph.invoke(Command(resume=answer), config=config, version="v2")