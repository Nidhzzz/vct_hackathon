import streamlit as st
import random
import time
import boto3
import json
import os
import pprint

# Set AWS credentials as environment variables (replace with your actual credentials)
os.environ['AWS_ACCESS_KEY_ID'] = 'AKIAXEVXYLCBOEGOHMC3'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'ohddYe2ka+nAQCJGOVKgtOjIOzPJyRECu39bL6eG'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'

# Create a session and Bedrock client
session = boto3.Session()
bedrock_client = session.client(service_name='bedrock-runtime')
bedrock_agent_client = session.client("bedrock-agent-runtime", region_name=os.environ['AWS_DEFAULT_REGION'])

# Pretty print for better output readability
pp = pprint.PrettyPrinter(indent=4)

# Function to retrieve text chunks from the knowledge base
def retrieve(query, kb_Id, numberOfResults=5):
    response = bedrock_agent_client.retrieve(
        retrievalQuery={'text': query},
        knowledgeBaseId=kb_Id,
        retrievalConfiguration={
            'vectorSearchConfiguration': {
                # 'numberOfResults': numberOfResults,
                'overrideSearchType': "HYBRID"  # optional
            }
        }
    )
    return response.get('results', [])

# Function to fetch contexts from retrieval results
def get_contexts(retrievalResults):
    contexts = []
    for retrievedResult in retrievalResults:
        contexts.append(retrievedResult['content']['text'])
    return contexts

# Function to interact with the foundation model using retrieved contexts
def generate_with_context(prompt, model_id='amazon.titan-text-premier-v1:0'):
    body = json.dumps({
        "inputText": prompt,
        "textGenerationConfig": {
            "maxTokenCount": 2000,
            "temperature": 0.1,
            "topP": 0.95
        }
    })
    
    response = bedrock_client.invoke_model(
        body=body,
        modelId=model_id,
        accept='application/json',
        contentType='application/json'
    )

    response_body = json.loads(response.get('body').read())
    return response_body.get('results', [{}])[0].get('outputText', 'No response generated.')

# =====================
st.markdown("## LLM-Powered Valorant Q&A Chatbot")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Add introductory prompt if no messages exist
if not st.session_state.messages:
    st.session_state.messages.append({"role": "assistant", "content": "Hello, how can I help you?"})

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Retrieveing reference prompt from the text file
predef_prompt = None
with open('prompt.txt', 'r') as f:
    file_content = f.read()
    predef_prompt = file_content

# Accept user input
if prompt := st.chat_input("If you don't like the answer give the same prompt again."):
    # Display user message in chat message container
    with st.chat_message("user"):
        # Step 1: Retrieve relevant contexts from the knowledge base
        kb_id = "VBL6UVD7KK"
        retrievalResults = retrieve(prompt, kb_id)
        contexts = get_contexts(retrievalResults)
        # Step 2: Build the prompt for the model using the retrieved contexts
        context_text = "\n".join(contexts) if contexts else "No relevant context found."
        full_prompt = f"""{predef_prompt}
        Context:
        {context_text}

        <question>
        {prompt}
        </question>

        The response should be specific and use statistics or numbers when possible to back up the decisions.
        """
        st.markdown(prompt)
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Display assistant response in chat message container
    with st.chat_message("assistant"):
        response = generate_with_context(full_prompt)
        st.markdown(response)
    # Add assistant response to chat history
    st.session_state.messages.append({"role": "assistant", "content": context_text})

    # st.session_state.messages.append({"role": "assistant", "content": response})
