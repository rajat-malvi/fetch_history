import os
import json
import asyncio
from typing import List
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    CacheMode,
    LLMConfig,
    LLMExtractionStrategy
)

# -------------------------------------------------------------------
# 1️⃣ Define Schema (same as original)
# -------------------------------------------------------------------
class UserData(BaseModel):
    """Schema for extracting LinkedIn profile data"""
    name: str = Field(..., description="The full name of the user as displayed on their LinkedIn profile")
    education: List[str] = Field(
        default_factory=list, 
        description="List of educational qualifications including degree, institution, and year if available"
    )
    experience: List[str] = Field(
        default_factory=list, 
        description="List of professional experiences including job title, company name, duration, and key responsibilities"
    )
    skills: List[str] = Field(
        default_factory=list,
        description="List of professional skills and competencies"
    )
    summary: str = Field(
        default="", 
        description="A comprehensive professional summary or about section from the profile"
    )
    current_position: str = Field(
        default="",
        description="Current job title and company"
    )

# -------------------------------------------------------------------
# 2️⃣ Initialize FastAPI
# -------------------------------------------------------------------
app = FastAPI(
    title="LinkedIn Profile Data Extractor",
    description="Extract structured data from LinkedIn profiles using Crawl4AI and Gemini LLM",
    version="1.0.0"
)

# -------------------------------------------------------------------
# 3️⃣ Core Extraction Function (same as your main() logic)
# -------------------------------------------------------------------
async def crawl_linkedin_profile(url: str):
    """Perform the full Crawl4AI extraction with identical config and prompt"""

    # Same LLM extraction strategy and instructions
    llm_strategy = LLMExtractionStrategy(
        llm_config=LLMConfig(
            provider="gemini/gemini-2.0-flash",
            api_token=os.getenv("GEMINI_API_KEY", "AIzaSyDXUBvJn8d_WhXl7R8exTn8w21ofuU5cAU")
        ),
        schema=UserData.model_json_schema(),
        extraction_type="schema",
        instruction="""
        Extract comprehensive information from the LinkedIn profile page. Focus on:
        1. Full name of the profile owner
        2. All educational qualifications (degrees, institutions, years)
        3. Complete work experience history (job titles, companies, dates, responsibilities)
        4. Professional skills listed on the profile
        5. Professional summary or about section
        6. Current job position and company
        
        Format all information clearly and completely. 
        If any field is not available, use empty string or empty list.
        Ensure the output is valid JSON matching the provided schema.
        """,
        chunk_token_threshold=2000,
        overlap_rate=0.1,
        apply_chunking=True,
        input_format="markdown",
        extra_args={"temperature": 0.0, "max_tokens": 2000}
    )

    # Same crawl configs as before
    crawl_config = CrawlerRunConfig(
        extraction_strategy=llm_strategy,
        cache_mode=CacheMode.BYPASS,
        word_count_threshold=10,
        exclude_external_links=True,
        exclude_social_media_links=True
    )

    # Same browser configuration
    browser_cfg = BrowserConfig(
        headless=True,
        verbose=False
    )

    context = {}

    try:
        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            print(f"🕷️ Crawling: {url}")
            result = await crawler.arun(url=url, config=crawl_config)

            context['markdown'] = getattr(result, 'markdown', "")

            if result.success and result.extracted_content:
                try:
                    data = json.loads(result.extracted_content)
                    context['json_response'] = data
                    llm_strategy.show_usage()  # same usage stats
                    return data

                except json.JSONDecodeError as e:
                    context['error'] = f"JSON parsing error: {e}"
                    raise HTTPException(status_code=500, detail=context['error'])
            else:
                error_msg = getattr(result, 'error_message', "Unknown crawl error")
                context['error'] = error_msg
                raise HTTPException(status_code=500, detail=error_msg)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Error: {str(e)}")

# -------------------------------------------------------------------
# 4️⃣ FastAPI Endpoints
# -------------------------------------------------------------------

@app.get("/")
def root():
    """Root endpoint"""
    return {
        "message": "Welcome to the LinkedIn Profile Extractor API",
        "usage": "Go to /docs to try the API interactively",
    }


@app.get("/extract_profile/", response_model=UserData)
async def extract_profile(url: str = Query(..., description="LinkedIn profile URL")):
    """
    Crawl and extract structured LinkedIn profile data.
    Example: /extract_profile/?url=https://www.linkedin.com/in/rajat-malvi/
    """
    data = await crawl_linkedin_profile(url)
    return data

# -------------------------------------------------------------------
# 5️⃣ Local Run Entry
# -------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
