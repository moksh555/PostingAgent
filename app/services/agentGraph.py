from datetime import datetime
import uuid
from pathlib import Path

from typing_extensions import TypedDict  # type: ignore

from langchain_core.prompts import ChatPromptTemplate  # type: ignore
from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore
from langgraph.checkpoint.memory import InMemorySaver   # type: ignore
from langgraph.runtime import Runtime  # type: ignore
from langgraph.errors import GraphInterrupt  # type: ignore
from langgraph.graph import StateGraph, START, END  # type: ignore
from langgraph.types import interrupt, RetryPolicy, Command  # type: ignore

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
    # TODO: # this is somehting I am planning to add later on as a feature, this will add more context for the user to generate next posts 
    # reasonForDelteion: list[str] 


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

                postIndex = currentLoopStartNumber + 1
                previousPostsSummary = "\n".join(
                    f"- Post {p.postNumber}: {p.content[:140]}..."
                    for p in postList
                ) or "(none yet — this is the first post in the campaign)"

                userInput = (
                    f"Marketing Note:\n{marketingNotes}\n\n"
                    f"This is post {postIndex} of {numberOfPosts} in the "
                    f"campaign.\n"
                    f"Campaign start date: {startDate}\n"
                    f"Platform: LinkedIn\n"
                    f"Source URL: {payload.url}\n"
                    f"Publish date for THIS post: use the campaign start "
                    f"date plus the appropriate offset per the scheduling "
                    f"rules in the system prompt, given this is post "
                    f"{postIndex}.\n\n"
                    f"Posts already accepted in this campaign (do not repeat "
                    f"their angle or hook):\n{previousPostsSummary}\n\n"
                    f"Generate exactly ONE post for slot {postIndex}."
                )

                postGenerated = chain.invoke({
                    "system_instruction": postGenerateSystemPrompt,
                    "user_input": userInput,
                })

                if postGenerated.content:
                    postGenerated.content = (
                        postGenerated.content
                        .replace("\\n", "\n")
                        .replace("\\t", "\t")
                    )

                if (
                    not postGenerated.content
                    or len(postGenerated.content.strip()) < 120
                    or not postGenerated.publishDate
                ):
                    raise FailedToBuildPosts(
                        "Failed to generate post: invalid / too-short response "
                        "from model"
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

            if postReGenerated.content:
                postReGenerated.content = (
                    postReGenerated.content
                    .replace("\\n", "\n")
                    .replace("\\t", "\t")
                )

            if (
                not postReGenerated.content
                or len(postReGenerated.content.strip()) < 120
                or not postReGenerated.publishDate
            ):
                raise FailedToBuildPosts(
                    "Failed to regenerate post: invalid / too-short response "
                    "from model"
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


workflow = StateGraph(AgentState)

workflow.add_node(
    "Validating_Payload", 
    receiverNode
    )
workflow.add_node(
    "Building_Marketing_Brief", 
    buildingMarketingBrief
    )
workflow.add_node(
    "Drafting_And_Reviewing_Posts", 
    generatingMarketingPosts,
    retry_policy=RetryPolicy(
        max_attempts=3,
        backoff_factor=3,
        retry_on = [FailedToBuildPosts],
    )
    )
workflow.add_node(
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


workflow.add_edge(START, "Validating_Payload")
workflow.add_edge("Validating_Payload", "Building_Marketing_Brief")
workflow.add_edge("Building_Marketing_Brief", "Drafting_And_Reviewing_Posts")

workflow.add_conditional_edges(
    "Drafting_And_Reviewing_Posts",
    routingGneratePostsNode,
    {
        "Regenerating_With_Feedback": "Regenerating_With_Feedback",
        "Drafting_And_Reviewing_Posts": "Drafting_And_Reviewing_Posts",
        END: END,
    },
)

workflow.add_conditional_edges(
    "Regenerating_With_Feedback",
    routingReGneratePostsNode,
    {
        "Regenerating_With_Feedback": "Regenerating_With_Feedback",
        "Drafting_And_Reviewing_Posts": "Drafting_And_Reviewing_Posts",
        END: END,
    },
)




