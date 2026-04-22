# Posting Agent

## About the Project

I am a big fan of the "Day in the Life of a Software Engineer" videos on YouTube. I was watching one of them where the person recording his day mentioned in the commentary that he was working with the marketing team for a new product launch. There are many things a marketer has to do when a new product or feature launches, and one of them is posting on social media and making sure the post gets the most reach. The best time to post depends on the targeted audience, content, and region. Content is the most critical part, and in the beginning, the marketing team — being non-technical — has to sit with engineers to understand the product and its documentation, figure out what they can post about, and how. The second piece is understanding the targeted audience and researching the best time to post in the targeted region.

So I am building this **Posting Agent** to automate the entire process, ensuring there are no delays for customers or end users using the product.

## What This Project Is

Posting Agent is an AI-powered marketing automation agent that takes a **documentation URL** as input and:

- Generates **marketing notes** based on the documentation.
- Decides the **content of the post(s)** and the **best timing** to post, based on data provided — either from the company's own data or from internet-based research.
- Produces **one or more posts per platform** (can generate multiple variations).
- Runs a **Human-in-the-Loop (HITL) workflow** where a human reviewer can take one of three actions on each post:
  - **Accept**
  - **Regenerate with feedback**
  - **Reject with feedback**
- Uses **AWS Lambda** and **Amazon EventBridge** to automatically publish the approved posts at the chosen day and time.

## What This Project Will Be

This will be launched first as an **MVP**. I will be onboarding a few of my friends to use it and work with it as early users. Based on their feedback, I will make the necessary changes and improvements before launching it to the world as a production-ready product.

## Tech Stack

- **Language:** Python
- **Agent Framework:** LangChain
- **Orchestration:** LangGraph
- **Backend / API:** FastAPI
- **Database:** DynamoDB
- **LLM:** Gemini models
- **Scheduling & Automation:** AWS Lambda, Amazon EventBridge, AWS EC2
