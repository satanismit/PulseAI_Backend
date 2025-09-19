from fastapi import APIRouter

router2=APIRouter()

@router2.get("/About")        
def About():

    return {
        "project": "PulseAI",
        "description": "An API that fetches the latest Indian news articles using RSS feeds.",
        "developer": "Smit Satani",
        "version": "1.0.0"
    }