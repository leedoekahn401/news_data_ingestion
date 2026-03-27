import streamlit as st
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from google.genai import types
from dotenv import load_dotenv
from google import genai
import os
import json
from pydantic import BaseModel, Field
from typing import Optional

st.set_page_config(page_title="News Ingestion App", layout="centered")

@st.cache_resource
def init_mongo():
    load_dotenv(override=True)
    db_uri = os.getenv('DB_URI')
    uri = db_uri
    mongo_client = MongoClient(uri, server_api=ServerApi('1'))
    return mongo_client['test']['news']

@st.cache_resource
def get_genai_client(api_key):
    return genai.Client(api_key=api_key)

collection = init_mongo()

AVAILABLE_MODELS = [
    "gemini-2.5-flash", 
    "gemini-2.5-pro", 
    "gemini-2.0-flash",
    "gemini-1.5-flash", 
    "gemini-1.5-pro"
]

class News(BaseModel):
    source: str = Field(description="Source of the news, or empty if fail")
    title: str = Field(description="Title of the news, or empty if fail")
    content: str = Field(description="The first two paragraph of the news, or empty if fail")
    date: str = Field(description="Time or date of the article in form of YYYY-MM-DDTHH:mm:ss.sssZ")
    error: Optional[str] = Field(default=None, description="Set this to 'Fail' if you cannot extract the link/data")

system_prompt = """
You are an automated data extraction assistant. Your sole purpose is to analyze news articles or headlines provided by the user and extract specific data points into a strict JSON format.

When you receive an article text or a headline, extract the following information:
1. The name of the news source.
2. The exact title of the article.
3. The exact text of the first two paragraphs of the article's main body.
4. The exact date or time of the article.
"""


#ui
st.title("News Ingestion UI")
with st.sidebar:
    st.header("Settings")
    user_api_key = st.text_input("Gemini API Key", type="password", help="Get your API key from Google AI Studio")
    selected_model = st.selectbox("Select Model", AVAILABLE_MODELS, index=0)

if not user_api_key:
    st.info(" Please enter your Gemini API key in the sidebar to continue.")
    st.stop()

try:
    genai_client = get_genai_client(user_api_key)
except Exception as e:
    st.error(f"Failed to initialize Gemini Client: {e}")
    st.stop()

if 'extracted_json' not in st.session_state:
    st.session_state.extracted_json = None

st.markdown("Paste news content or headlines below to extract them into MongoDB.")

prompt = st.text_area("News Content", height=200, placeholder="Paste your news text here...")

if st.button("Extract Data", type="primary"):
    if not prompt.strip():
        st.warning("Please enter some text.")
    else:
        with st.spinner("Analyzing with Gemini..."):
            try:
                response = genai_client.models.generate_content(
                    model=selected_model,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        response_mime_type="application/json",
                        response_schema=News
                    ),
                    contents=prompt
                )
                data = json.loads(response.text)
                st.session_state.extracted_json = data
                
            except Exception as e:
                st.error(f"Error extracting data: {e}")

if st.session_state.extracted_json:
    st.subheader("Extracted JSON")
    st.json(st.session_state.extracted_json)
    
    st.markdown("---")
    st.markdown("**Does the data look good?**")
    
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("Save to DB"):
            try:
                collection.insert_one(st.session_state.extracted_json.copy())
                st.success("Successfully inserted into MongoDB!")
                st.session_state.extracted_json = None
            except Exception as e:
                st.error(f"Failed to insert into database: {e}")
    
    with col2:
        if st.button("Discard"):
            st.session_state.extracted_json = None
            st.rerun()
