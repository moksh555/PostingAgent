import json
from datetime import datetime
from operator import add
from typing_extensions import TypedDict, Annotated  # type: ignore
from langchain_core.prompts import ChatPromptTemplate  # type: ignore
from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore
from langgraph.runtime import Runtime  # type: ignore
from langgraph.errors import GraphInterrupt  # type: ignore
from langgraph.graph import StateGraph, START, END  # type: ignore
from langgraph.types import interrupt, RetryPolicy  # type: ignore
from configurations.config import config
from app.api.depends.repositoryDepends import get_s3_connection
from app.errorsHandler.errors import (
    NoPayloadError,
    NoURLError,
    NoUserIdError,
    NoNumberOfPostsError,
    NoStartDateError,
    FailedToBuildMarketingBriefError,
    FailedToBuildPosts,
    FailedToWriteSummaryToS3,
    FailedToSaveFinalPostData
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
from app.api.depends.repositoryDepends import get_postgres_repository_posts
from app.repository.s3connection import S3Connection

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
structuredPostGenerationLLM = PostGenerationLLM.with_structured_output(
    LLMPostGeneration
)


class AgentState(TypedDict):
    payload: AgentRunRequest
    notes: AgentSummary
    posts: Annotated[list[AgentPost], add]
    regeneratePost: bool
    postRegenerationDescription: str
    postToRegenerate: LLMPostGeneration
    currentLoopStartNumber: int
    cacheDraft: LLMPostGeneration
    # TODO: # this is somehting I am planning to add later on as a feature, this will add more context for the user to generate next posts
    # reasonForDelteion: list[str]

async def writeSummaryToS3(notes: AgentSummary, userId: str) -> str:
    try:
        await get_s3_connection().put_object(
            body=notes.marketingBrief,
            bucketName=config.AWS_BUCKET_NAME,
            key=f"UserNotes/{userId}/{notes.fileName}",
        )
        return f"https://{config.AWS_BUCKET_NAME}.s3.{config.AWS_DEFAULT_REGION}.amazonaws.com/UserNotes/{userId}/{notes.fileName}"
    except FailedToWriteSummaryToS3:
        raise
    except Exception as e:
        raise FailedToWriteSummaryToS3(f"Failed to write summary to S3 with connection error: {e}") from e


async def receiverNode(state: AgentState):
    payload = state.get("payload")
    if payload is None:
        raise NoPayloadError("No payload found during Agentic RAG Flow")
    elif payload.userId is None:
        raise NoUserIdError("No user ID found during Agentic RAG Flow")
    elif payload.url is None:
        raise NoURLError("No URL found during Agentic RAG Flow")
    elif payload.numberOfPosts is None:
        raise NoNumberOfPostsError("No number of posts found during Agentic RAG Flow")
    elif payload.startDate is None:
        raise NoStartDateError("No start date found during Agentic RAG Flow")
    return {}


async def lookingForKnowledgefromPrviousNotes(state: AgentState):
    pass


async def buildingMarketingBrief(state: AgentState):
    payload = state.get("payload")

    prompt = MARKETING_BRIEF_PROMPT.format(
        url=payload.url,
        number_of_posts=payload.numberOfPosts,
    )

    try:
        response = await structuredSummaryLLM.ainvoke(prompt)

        if (
            response.marketingBrief is None
            or response.marketingBrief == ""
            or response.fileName is None
            or response.fileName == ""
        ):
            raise FailedToBuildMarketingBriefError("Response from model is invalid")

        return {"notes": response}
    except FailedToBuildMarketingBriefError:
        raise
    except Exception as e:
        raise FailedToBuildMarketingBriefError(
            f"Failed to build marketing brief: {e}"
        ) from e


async def generatingMarketingPosts(state: AgentState):
    notes = state.get("notes")
    marketingNotes = notes.marketingBrief
    payload = state.get("payload")
    numberOfPosts = payload.numberOfPosts
    startDate = state.get("payload").startDate
    postList = state.get("posts") or []
    currentLoopStartNumber = state.get("currentLoopStartNumber") or 0
    postGenerateSystemPrompt = POST_GENERATION_PROMPT
    cacheDraft = state.get("cacheDraft")

    try:
        for loop_i in range(currentLoopStartNumber, numberOfPosts):
            post_slot = loop_i + 1  # 1-based post number in campaign
            if cacheDraft is not None:
                postGenerated = cacheDraft
            else:
                prompt = ChatPromptTemplate.from_messages(
                    [
                        ("system", "{system_instruction}"),
                        ("human", "{user_input}"),
                    ]
                )

                chain = prompt | structuredPostGenerationLLM

                postIndex = post_slot
                previousPostsSummary = (
                    "\n".join(
                        f"- Post {p.postNumber}: {p.content[:140]}..." for p in postList
                    )
                    or "(none yet — this is the first post in the campaign)"
                )

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

                postGenerated = await chain.ainvoke(
                    {
                        "system_instruction": postGenerateSystemPrompt,
                        "user_input": userInput,
                    }
                )

                if postGenerated.content:
                    postGenerated.content = postGenerated.content.replace(
                        "\\n", "\n"
                    ).replace("\\t", "\t")

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
                }

            answer: AgentPostGenerationInterrupt = interrupt(
                {
                    "postContent": postGenerated.content,
                    "publishDate": postGenerated.publishDate,
                    "actions": ["Accept", "Reject", "Regenerate"],
                }
            )

            if answer.actions == "Accept":
                acceptedPosts = AgentPost(
                        content=postGenerated.content,
                        publishDate=postGenerated.publishDate,
                        platform="LinkedIn",
                        postNumber=len(postList) + 1,
                    )
                
                return {    
                    "posts": [acceptedPosts],
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


async def regeneratePost(state: AgentState):
    notes = state.get("notes")
    marketingNotes = notes.marketingBrief
    payload = state.get("payload")
    postToRegenerate = state.get("postToRegenerate")
    postRegenerationDescription = state.get("postRegenerationDescription")
    postGenerateSystemPrompt = POST_REGENERATION_PROMPT
    postsList = state.get("posts") or []
    cacheDraft = state.get("cacheDraft")
    number_of_posts = payload.numberOfPosts
    reg_slot = len(postsList) + 1
    _reg_loop = f"loop {reg_slot}/{number_of_posts}"

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "{system_instruction}"),
            ("human", "{user_input}"),
        ]
    )
    chain = prompt | structuredPostGenerationLLM

    try:
        if cacheDraft is not None:
            postReGenerated = cacheDraft
        else:
            postReGenerated = await chain.ainvoke(
                {
                    "system_instruction": postGenerateSystemPrompt,
                    "user_input": f"Here is the input 'postToRegenerate': {postToRegenerate.content}, 'postRegenerationDescription': {postRegenerationDescription}, 'Notes': {marketingNotes}, url: {payload.url}, publishDate: {postToRegenerate.publishDate}",
                }
            )

            if postReGenerated.content:
                postReGenerated.content = postReGenerated.content.replace(
                    "\\n", "\n"
                ).replace("\\t", "\t")

            if (
                not postReGenerated.content
                or len(postReGenerated.content.strip()) < 120
                or not postReGenerated.publishDate
            ):
                raise FailedToBuildPosts(
                    "Failed to regenerate post: invalid / too-short response from model"
                )

            return {
                "cacheDraft": postReGenerated,
            }

        answer: AgentPostGenerationInterrupt = interrupt(
            {
                "postContent": postReGenerated.content,
                "publishDate": postReGenerated.publishDate,
                "actions": ["Accept", "Reject", "Regenerate"],
            }
        )

        if answer.actions == "Regenerate":
            return {
                "regeneratePost": True,
                "postRegenerationDescription": answer.postChangeDescription,
                "postToRegenerate": postReGenerated,
                "cacheDraft": None,
            }
        elif answer.actions == "Accept":
            acceptedPosts = AgentPost(
                    content=postReGenerated.content,
                    publishDate=postReGenerated.publishDate,
                    platform="LinkedIn",
                    postNumber=len(postsList) + 1,
                )
            return {
                "posts": [acceptedPosts],
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
        else:
            raise FailedToBuildPosts(
                f"Invalid action received: {answer.actions!r}. "
                f"Expected one of: 'Accept', 'Reject', 'Regenerate'"
            )
    except GraphInterrupt:
        raise
    except FailedToBuildPosts:
        raise
    except Exception as e:
        raise FailedToBuildPosts(f"Failed to regenerate post: {e}") from e

async def saveDataToDatabase(state: AgentState, runtime: Runtime):
    payload = state.get("payload")
    posts = state.get("posts")
    notes = state.get("notes")
    threadId = runtime.execution_info.thread_id

    try: 
        notesUrl = await writeSummaryToS3(
            notes, 
            payload.userId
        )
        createdata = []
        for post in posts or []:
            createdata.append(
                (
                    payload.userId,
                    payload.url,
                    post.platform,
                    post.content,
                    post.publishDate,
                    threadId,
                    datetime.now(),
                    notesUrl,
                )
            )
        try:
            postgresRepository = await get_postgres_repository_posts()
            await postgresRepository.saveFinalPostDataExecuteMany(createdata)
        except Exception as e:
            raise FailedToSaveFinalPostData(f"Failed to save final post data: {e}") from e

        return {}
    except FailedToSaveFinalPostData:
        raise
    except FailedToWriteSummaryToS3:
        raise
    except Exception as e:
        raise FailedToWriteSummaryToS3(f"Failed to write summary to S3: {e}") from e

workflow = StateGraph(AgentState)

workflow.add_node(
    "Validating_Payload", 
    receiverNode
    )

workflow.add_node(
    "Building_Marketing_Brief", 
    buildingMarketingBrief)

workflow.add_node(
    "Drafting_And_Reviewing_Posts",
    generatingMarketingPosts,
    retry_policy=RetryPolicy(
        max_attempts=3,
        backoff_factor=3,
        retry_on=[FailedToBuildPosts],
    ),
)
workflow.add_node(
    "Regenerating_With_Feedback",
    regeneratePost,
    retry_policy=RetryPolicy(
        max_attempts=3,
        backoff_factor=3,
        retry_on=[FailedToBuildPosts],
    ),
)

workflow.add_node(
    "Saving_Data_To_Database", 
    saveDataToDatabase
    )

def routingGneratePostsNode(state: AgentState):
    if state.get("regeneratePost"):
        nxt = "Regenerating_With_Feedback"
    elif (state.get("currentLoopStartNumber") or 0) < state.get(
        "payload"
    ).numberOfPosts:
        nxt = "Drafting_And_Reviewing_Posts"
    else:
        nxt = "Saving_Data_To_Database"
    return nxt


def routingReGneratePostsNode(state: AgentState):
    if not state.get("regeneratePost"):
        nxt = "Drafting_And_Reviewing_Posts"
    else:
        nxt = "Regenerating_With_Feedback"      
    return nxt


workflow.add_edge(START, "Validating_Payload")
workflow.add_edge("Validating_Payload", "Building_Marketing_Brief")
workflow.add_edge("Building_Marketing_Brief", "Drafting_And_Reviewing_Posts")

workflow.add_conditional_edges(
    "Drafting_And_Reviewing_Posts",
    routingGneratePostsNode,
    {
        "Regenerating_With_Feedback": "Regenerating_With_Feedback",
        "Drafting_And_Reviewing_Posts": "Drafting_And_Reviewing_Posts",
        "Saving_Data_To_Database": "Saving_Data_To_Database",
    },
)

workflow.add_conditional_edges(
    "Regenerating_With_Feedback",
    routingReGneratePostsNode,
    {
        "Regenerating_With_Feedback": "Regenerating_With_Feedback",
        "Drafting_And_Reviewing_Posts": "Drafting_And_Reviewing_Posts",
    },
)

workflow.add_edge("Saving_Data_To_Database", END)
