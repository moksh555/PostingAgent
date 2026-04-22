from pathlib import Path

from typing_extensions import TypedDict  # type: ignore

from langchain_core.prompts import ChatPromptTemplate  # type: ignore
from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore
from langgraph.checkpoint.memory import InMemorySaver   # type: ignore
from langgraph.runtime import Runtime  # type: ignore
from langgraph.errors import GraphInterrupt  # type: ignore
from langgraph.graph import StateGraph, START, END  # type: ignore
from langgraph.types import interrupt, RetryPolicy  # type: ignore

from configurations.config import config

from app.errorsHandler import (
    NoPayloadError,
    NoURLError,
    NoNumberOfPostsError,
    NoStartDateError,
    FailedToBuildMarketingBriefError,
    FailedToBuildPosts,
)
from app.models.AgentModels import (
    AgentRunRequest,
    AgentSummary,
    LLMPostGeneration,
    AgentPost,
    AgentPostGenerationInterrupt,
)
from app.prompts.detailedDescription import MARKETING_BRIEF_PROMPT
from app.prompts.postGenerationPrompt import POST_GENERATION_PROMPT
from app.prompts.postRegenerationPrompt import POST_REGENERATION_PROMPT


# TODO: Later on will have model selection for the user so we can use the best model for the task
LLM = ChatGoogleGenerativeAI(
    model="gemini-3-flash-preview",
    google_api_key=config.GEMINI_API_KEY,
)
structuredSummaryLLM = LLM.with_structured_output(AgentSummary)

PostGenerationLLM = ChatGoogleGenerativeAI(
    model="gemini-3-flash-preview",
    google_api_key=config.GEMINI_API_KEY,
)
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
    currentLoopStartNumber: int
    cacheDraft: LLMPostGeneration


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

        if (
            response.marketingBrief is None
            or response.marketingBrief == ""
            or response.fileName is None
            or response.fileName == ""
        ):
            raise FailedToBuildMarketingBriefError("Response from model is invalid")

        writeSummaryToFile(response)
        return {"marketingNotes": response.marketingBrief}
    except Exception as e:
        raise FailedToBuildMarketingBriefError(f"Failed to build marketing brief: {e}")


def generatingMarketingPosts(state: AgentState, runtime: Runtime):
    marketingNotes = state.get("marketingNotes")
    payload = state.get("payload")
    numberOfPosts = payload.numberOfPosts
    startDate = state.get("payload").startDate
    postList = state.get("posts") or []
    currentLoopStartNumber = state.get("currentLoopStartNumber") or 0
    postGenerateSystemPrompt = POST_GENERATION_PROMPT
    cacheDraft = state.get("cacheDraft")

    try:
        for _ in range(currentLoopStartNumber, numberOfPosts):

            if cacheDraft is not None:
                postGenerated = cacheDraft
            else:
                prompt = ChatPromptTemplate.from_messages([
                    ("system", "{system_instruction}"),
                    ("human", "{user_input}"),
                ])

                chain = prompt | structuredPostGenerationLLM

                postGenerated = chain.invoke({
                    "system_instruction": postGenerateSystemPrompt,
                    "user_input": f"Here is the input 'Marketing Note': {marketingNotes}, 'numberOfPosts': {numberOfPosts}, 'startDate': {startDate}, 'platform': 'LinkedIn', 'url': {payload.url}",
                })

                if (
                    postGenerated.content is None
                    or postGenerated.content == ""
                    or postGenerated.publishDate is None
                    or postGenerated.publishDate == ""
                ):
                    raise FailedToBuildPosts(
                        f"Failed to generate post: Invalid response from model"
                    )

                return {
                    "cacheDraft": postGenerated,
                    "posts": postList,
                }

            answer: AgentPostGenerationInterrupt = interrupt({
                "postContent": postGenerated.content,
                "publishDate": postGenerated.publishDate,
                "actions": ["Accept", "Reject", "Regenerate"],
            })

            if answer.actions == "Accept":
                postList.append(AgentPost(
                    content=postGenerated.content,
                    publishDate=postGenerated.publishDate,
                    platform="LinkedIn",
                    postNumber=len(postList) + 1,
                ))
                return {
                    "posts": postList,
                    "cacheDraft": None,
                    "currentLoopStartNumber": currentLoopStartNumber + 1,
                }
            elif answer.actions == "Reject":
                return {
                    "cacheDraft": None,
                    "currentLoopStartNumber": currentLoopStartNumber + 1,
                }
            elif answer.actions == "Regenerate":
                return {
                    "regeneratePost": True,
                    "postRegenerationDescription": answer.postChangeDescription,
                    "postToRegenerate": postGenerated,
                    "cacheDraft": None,
                    "currentLoopStartNumber": currentLoopStartNumber + 1,
                }
    except GraphInterrupt:
        raise
    except FailedToBuildPosts:
        raise
    except Exception as e:
        raise FailedToBuildPosts(f"Failed to build posts: {e}") from e


def regeneratePost(state: AgentState, runtime: Runtime):
    marketingNotes = state.get("marketingNotes")
    payload = state.get("payload")
    postToRegenerate = state.get("postToRegenerate")
    postRegenerationDescription = state.get("postRegenerationDescription")
    postGenerateSystemPrompt = POST_REGENERATION_PROMPT
    postsList = state.get("posts") or []
    cacheDraft = state.get("cacheDraft")

    prompt = ChatPromptTemplate.from_messages([
        ("system", "{system_instruction}"),
        ("human", "{user_input}"),
    ])
    chain = prompt | structuredPostGenerationLLM

    try:
        if cacheDraft is not None:
            postReGenerated = cacheDraft
        else:
            postReGenerated = chain.invoke({
                "system_instruction": postGenerateSystemPrompt,
                "user_input": f"Here is the input 'postToRegenerate': {postToRegenerate.content}, 'postRegenerationDescription': {postRegenerationDescription}, 'Notes': {marketingNotes}, url: {payload.url}, publishDate: {postToRegenerate.publishDate}",
            })

            if (
                postReGenerated.content is None
                or postReGenerated.content == ""
                or postReGenerated.publishDate is None
                or postReGenerated.publishDate == ""
            ):
                raise FailedToBuildPosts(
                    f"Failed to regenerate post: Invalid response from model"
                    )

            return {
                "cacheDraft": postReGenerated,
            }

        answer: AgentPostGenerationInterrupt = interrupt({
            "postContent": postReGenerated.content,
            "publishDate": postReGenerated.publishDate,
            "actions": ["Accept", "Reject", "Regenerate"],
        })

        if answer.actions == "Regenerate":
            return {
                "regeneratePost": True,
                "postRegenerationDescription": answer.postChangeDescription,
                "postToRegenerate": postReGenerated,
                "cacheDraft": None,
            }
        elif answer.actions == "Accept":
            postsList.append(AgentPost(
                content=postReGenerated.content,
                publishDate=postReGenerated.publishDate,
                platform="LinkedIn",
                postNumber=len(postsList) + 1,
            ))
            return {
                "posts": postsList,
                "regeneratePost": False,
                "postRegenerationDescription": "",
                "postToRegenerate": None,
                "cacheDraft": None,
            }
        elif answer.actions == "Reject":
            return {
                "regeneratePost": False,
                "postRegenerationDescription": "",
                "postToRegenerate": None,
                "cacheDraft": None,
            }
    except GraphInterrupt:
        raise
    except FailedToBuildPosts:
        raise
    except Exception as e:
        raise FailedToBuildPosts(f"Failed to regenerate post: {e}") from e


graph = StateGraph(AgentState)

graph.add_node(
    "Validating_Payload", 
    receiverNode
    )
graph.add_node(
    "Building_Marketing_Brief", 
    buildingMarketingBrief
    )
graph.add_node(
    "Drafting_And_Reviewing_Posts", 
    generatingMarketingPosts,
    retry_policy=RetryPolicy(
        max_attempts=3,
        backoff_factor=3,
        retry_on = [FailedToBuildPosts],
    )
    )
graph.add_node(
    "Regenerating_With_Feedback", 
    regeneratePost,
    retry_policy=RetryPolicy(
        max_attempts=3,
        backoff_factor=3,
        retry_on = [FailedToBuildPosts],
    ),
    )


def routingGneratePostsNode(state: AgentState):
    if state.get("regeneratePost"):
        return "Regenerating_With_Feedback"
    elif (state.get("currentLoopStartNumber") or 0) < state.get("payload").numberOfPosts:
        return "Drafting_And_Reviewing_Posts"
    return END


def routingReGneratePostsNode(state: AgentState):
    if not state.get("regeneratePost"):
        return "Drafting_And_Reviewing_Posts"
    return "Regenerating_With_Feedback"


graph.add_edge(START, "Validating_Payload")
graph.add_edge("Validating_Payload", "Building_Marketing_Brief")
graph.add_edge("Building_Marketing_Brief", "Drafting_And_Reviewing_Posts")

graph.add_conditional_edges(
    "Drafting_And_Reviewing_Posts",
    routingGneratePostsNode,
    {
        "Regenerating_With_Feedback": "Regenerating_With_Feedback",
        "Drafting_And_Reviewing_Posts": "Drafting_And_Reviewing_Posts",
        END: END,
    },
)

graph.add_conditional_edges(
    "Regenerating_With_Feedback",
    routingReGneratePostsNode,
    {
        "Regenerating_With_Feedback": "Regenerating_With_Feedback",
        "Drafting_And_Reviewing_Posts": "Drafting_And_Reviewing_Posts",
        END: END,
    },
)

checkpointer = InMemorySaver()
graph = graph.compile(checkpointer=checkpointer)

# if __name__ == "__main__":
#     config = {"configurable": {"thread_id": uuid.uuid4()}}
#     for chunk in graph.stream(
#         {"payload": AgentRunRequest(url="https://code.claude.com/docs/en/agent-sdk/overview", numberOfPosts=1, startDate=datetime.now())},
#         config=config,
#         version="v2"):
#         if chunk["type"] == "updates":
#             for node_name, state in chunk["data"].items():
#                 print(f"Node {node_name}")
#                 if node_name == "__interrupt__":
#                     answer = AgentPostGenerationInterrupt(actions="Accept")
#                     graph.invoke(Command(resume=answer), config=config, version="v2")
