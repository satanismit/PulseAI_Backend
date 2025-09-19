from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from routes.news import router
from routes.about import router2
from scraping import fetcher
from typing import List, Dict, Any

import google.generativeai as genai
import os
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import json
from datetime import datetime

load_dotenv()
# Also try loading from parent directory
load_dotenv("../.env")

# Debug environment loading
print("=== Environment Debug ===")
print(f"Current working directory: {os.getcwd()}")
print(f"GEMINI_API_KEY loaded: {bool(os.getenv('GEMINI_API_KEY'))}")
print(f"SENDER_EMAIL: {os.getenv('SENDER_EMAIL')}")
print(f"SENDER_PASSWORD exists: {bool(os.getenv('SENDER_PASSWORD'))}")
print("========================")

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

app = FastAPI(title="PulseAI")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173","https://smitpulseai.netlify.app"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/articles")
def get_all_articles():
    if fetcher.mongodb_available and fetcher.collection is not None:
        articles = list(fetcher.collection.find({}, {"_id": 0}))  # exclude MongoDB _id
        return {"articles": articles}
    return {"articles": []}

@app.post("/scrape")
def scrape_and_store(n: int = 20):
    result = fetcher.get_news(n)
    return {
        "message": result.get("message", f"Scraped {result.get('total', 0)} articles"),
        "articles": result.get("articles", []),
        "total": result.get("total", 0)
    }

# Request body models
class ChatRequest(BaseModel):
    query: str

class EmailRequest(BaseModel):
    email: str
    articles: List[Dict[str, Any]]

class WhatsAppRequest(BaseModel):
    whatsapp: str
    articles: List[Dict[str, Any]]


@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        
        # Enhanced prompt for concise, clear responses
        enhanced_prompt = f"""
        Please provide a clear and concise response to the following query.
        Follow these guidelines:
        - Be direct and to the point
        - Use simple, plain text only (no markdown formatting)
        - Keep responses under 5 sentences when possible
        - Use simple bullet points with dashes (-)
        - Do not use bold, italic, or any special formatting
        - Skip unnecessary introductions
        - Focus on the most relevant information
        - Write in plain text without asterisks, underscores, or special characters
        
        Query: {request.query}
        
        Respond in plain text that's easy to read.
        """
        
        response = model.generate_content(enhanced_prompt)
        
        # Clean up the response text - remove all markdown formatting
        clean_text = response.text.strip()
        
        # Remove markdown headers
        clean_text = clean_text.replace('## ', '').replace('### ', '').replace('# ', '')
        
        # Remove bold formatting
        clean_text = clean_text.replace('**', '')
        
        # Remove italic formatting
        clean_text = clean_text.replace('*', '')
        
        # Remove other common markdown elements
        clean_text = clean_text.replace('_', '')
        clean_text = clean_text.replace('`', '')
        
        # Clean up extra whitespace
        import re
        clean_text = re.sub(r'\n\s*\n', '\n\n', clean_text)  # Multiple newlines to double
        clean_text = re.sub(r' +', ' ', clean_text)  # Multiple spaces to single
        
        # Parse and structure the response
        formatted_response = {
            "text": clean_text,
            "formatted": True,
            "sections": parse_response_sections(clean_text)
        }
        
        return formatted_response
    except Exception as e:
        return {"error": str(e)}

def parse_response_sections(text):
    """Parse the response text into structured sections"""
    sections = []
    lines = text.split('\n')
    current_section = {"type": "paragraph", "content": []}
    
    for line in lines:
        line = line.strip()
        if not line:
            if current_section["content"]:
                # Only add paragraph if it has content
                if any(part.strip() for part in current_section["content"]):
                    sections.append(current_section)
                current_section = {"type": "paragraph", "content": []}
            continue
            
        # Check for bullet points (simplified for cleaner output)
        if line.startswith(('- ', '• ', '* ')):
            if current_section["type"] != "bullet_list":
                if current_section["content"] and any(part.strip() for part in current_section["content"]):
                    sections.append(current_section)
                current_section = {"type": "bullet_list", "content": []}
            current_section["content"].append(line[2:])
        else:
            # Regular paragraph text
            if current_section["type"] != "paragraph":
                if current_section["content"]:
                    sections.append(current_section)
                current_section = {"type": "paragraph", "content": []}
            current_section["content"].append(line)
    
    # Add the last section
    if current_section["content"]:
        sections.append(current_section)
    
    return sections

def format_articles_for_email(articles):
    """Format articles for email content"""
    email_content = """
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
            .header { background: #667eea; color: white; padding: 20px; text-align: center; }
            .article { border: 1px solid #ddd; margin: 20px 0; padding: 15px; border-radius: 8px; }
            .source { background: #667eea; color: white; padding: 5px 10px; border-radius: 15px; font-size: 12px; }
            .title { color: #1e293b; font-size: 18px; font-weight: bold; margin: 10px 0; }
            .summary { color: #64748b; margin: 10px 0; }
            .link { color: #667eea; text-decoration: none; }
            .footer { text-align: center; color: #64748b; margin-top: 30px; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📰 Your News Update from PulseAI</h1>
            <p>Here are your selected news articles</p>
        </div>
    """
    
    for article in articles:
        email_content += f"""
        <div class="article">
            <span class="source">{article.get('source', 'Unknown')}</span>
            <h2 class="title">{article.get('title', 'No Title')}</h2>
            <p class="summary">{article.get('summary', 'No summary available')}</p>
            <p><strong>Published:</strong> {article.get('published', 'Unknown date')}</p>
            <p><a href="{article.get('link', '#')}" class="link" target="_blank">Read Full Article →</a></p>
        </div>
        """
    
    email_content += """
        <div class="footer">
            <p>Powered by PulseAI - Intelligent News Without Overload</p>
            <p>This email was sent because you requested news updates through our platform.</p>
        </div>
    </body>
    </html>
    """
    
    return email_content

def format_articles_for_whatsapp(articles):
    """Format articles for WhatsApp message"""
    message = "📰 *Your News Update from PulseAI*\n\n"
    
    for i, article in enumerate(articles, 1):
        message += f"*{i}. {article.get('title', 'No Title')}*\n"
        message += f"📍 Source: {article.get('source', 'Unknown')}\n"
        message += f"📅 {article.get('published', 'Unknown date')}\n\n"
        message += f"{article.get('summary', 'No summary available')}\n\n"
        if article.get('link'):
            message += f"🔗 Read more: {article.get('link')}\n\n"
        message += "─────────────────\n\n"
    
    message += "Powered by PulseAI 🤖\n"
    message += "Intelligent News Without Overload"
    
    return message

@app.post("/send-email")
async def send_email(request: EmailRequest):
    try:
        # Email configuration from environment variables
        smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        sender_email = os.getenv("SENDER_EMAIL")
        sender_password = os.getenv("SENDER_PASSWORD")
        
        print(f"Debug - SENDER_EMAIL: {sender_email}")
        print(f"Debug - SENDER_PASSWORD exists: {bool(sender_password)}")
        print(f"Debug - SMTP_SERVER: {smtp_server}")
        print(f"Debug - SMTP_PORT: {smtp_port}")
        
        if not sender_email or not sender_password:
            raise HTTPException(
                status_code=500, 
                detail=f"Email configuration not found. SENDER_EMAIL: {bool(sender_email)}, SENDER_PASSWORD: {bool(sender_password)}"
            )
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"📰 News Update from PulseAI - {len(request.articles)} Articles"
        msg['From'] = sender_email
        msg['To'] = request.email
        
        # Create HTML content
        html_content = format_articles_for_email(request.articles)
        html_part = MIMEText(html_content, 'html')
        msg.attach(html_part)
        
        # Send email
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        
        return {
            "success": True,
            "message": f"Successfully sent {len(request.articles)} articles to {request.email}"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")

@app.post("/send-whatsapp")
async def send_whatsapp(request: WhatsAppRequest):
    try:
        # WhatsApp API configuration from environment variables
        whatsapp_token = os.getenv("WHATSAPP_TOKEN")
        whatsapp_phone_id = os.getenv("WHATSAPP_PHONE_ID")
        
        # For testing purposes, if WhatsApp credentials are not configured,
        # we'll simulate the sending and save to a file instead
        if not whatsapp_token or not whatsapp_phone_id or whatsapp_token == "your_whatsapp_business_api_token":
            # Format message
            message_text = format_articles_for_whatsapp(request.articles)
            
            # Save to file for testing
            timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            filename = f"whatsapp_message_{timestamp}.txt"
            
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(f"WhatsApp Message for: {request.whatsapp}\n")
                    f.write(f"Timestamp: {datetime.now()}\n")
                    f.write("="*50 + "\n\n")
                    f.write(message_text)
                
                return {
                    "success": True,
                    "message": f"WhatsApp simulation: Message saved to {filename}. {len(request.articles)} articles prepared for {request.whatsapp}",
                    "simulation": True
                }
            except Exception as e:
                print(f"Error saving WhatsApp simulation: {e}")
                return {
                    "success": True,
                    "message": f"WhatsApp simulation successful: {len(request.articles)} articles prepared for {request.whatsapp}",
                    "simulation": True
                }
        
        # Real WhatsApp API implementation
        # Format message
        message_text = format_articles_for_whatsapp(request.articles)
        
        # WhatsApp Business API endpoint
        url = f"https://graph.facebook.com/v17.0/{whatsapp_phone_id}/messages"
        
        headers = {
            "Authorization": f"Bearer {whatsapp_token}",
            "Content-Type": "application/json"
        }
        
        # Clean phone number (remove non-digits except +)
        phone_number = ''.join(c for c in request.whatsapp if c.isdigit() or c == '+')
        if not phone_number.startswith('+'):
            phone_number = '+' + phone_number
        
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "text",
            "text": {
                "body": message_text
            }
        }
        
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 200:
            return {
                "success": True,
                "message": f"Successfully sent {len(request.articles)} articles to {request.whatsapp}"
            }
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"WhatsApp API error: {response.text}"
            )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send WhatsApp message: {str(e)}")


# Include other routers
app.include_router(router)
app.include_router(router2)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app",host="127.0.0.1", port=8000, reload=True)
