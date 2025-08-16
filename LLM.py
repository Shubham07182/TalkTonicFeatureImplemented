import streamlit as st
import re
import requests
import html
import json
import pandas as pd
import csv
import io
import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")


def call_groq_model(message, model="llama3-8b-8192"):
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GROQ_API_KEY}"
        }
        data = {"model": model, "messages": [{"role": "user", "content": message}]}
        resp = requests.post(url, headers=headers, json=data, timeout=20)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[Error calling Groq LLM: {e}]"

def web_search_with_google_custom_search(query):
    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {"key": GOOGLE_API_KEY, "cx": SEARCH_ENGINE_ID, "q": query, "num": 5}
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if "items" not in data or not data["items"]:
            return "No relevant results found."

        top_snippets = []
        for item in data["items"][:5]:
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            link = item.get("link", "")
            top_snippets.append(f"{title} — {snippet} ({link})")

        summary_prompt = "Summarize the following search snippets concisely in 3 sentences:\n\n" + "\n\n".join(top_snippets)
        summary = call_groq_model(summary_prompt)

        results_md = "\n\nTop Results:\n"
        for i, item in enumerate(data["items"][:5], start=1):
            results_md += f"{i}. {item.get('title','No title')} — {item.get('link','')}\n"

        return f"Search Summary:\n{summary}\n\n{results_md}"
    except Exception as e:
        return f"[Error during Google Custom Search: {e}]"

def strip_html_tags(text):
    return re.sub(r"<[^>]*>", "", text)

def summarize_website(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; TalkTonic/1.0)"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        text = strip_html_tags(resp.text)
        text = re.sub(r"\s+", " ", text).strip()
        snippet = text[:3500]
        prompt = f"Summarize the following webpage content in 3-4 sentences:\n\n{snippet}"
        return call_groq_model(prompt)
    except Exception as e:
        return f"[Error summarizing website: {e}]"

def detect_input_type(text):
    t = text.strip()
    if t.startswith("{") or t.startswith("["):
        return "json"
    if t.lower().startswith("http://") or t.lower().startswith("https://"):
        return "url"
    if ("\n" in t) and ("," in t):
        return "csv"
    return "chat"

def format_data(data, format_type):
    try:
        if format_type == "json_to_csv":
            json_data = json.loads(data)
            if isinstance(json_data, dict):
                json_data = [json_data]
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=json_data[0].keys())
            writer.writeheader()
            writer.writerows(json_data)
            return output.getvalue()
        elif format_type == "upper":
            return data.upper()
        elif format_type == "lower":
            return data.lower()
        else:
            return "Unsupported format type."
    except Exception as e:
        return f"Data format error: {e}"

def is_url(text):
    return bool(re.match(r"^https?://", text.strip(), re.IGNORECASE))

def is_csv(text):
    return "," in text and "\n" in text


if "messages" not in st.session_state:
    st.session_state.messages = []

st.markdown("""
<style>
.chat-container {height: 480px; overflow-y: auto; border: 1px solid #444; padding: 12px;
    border-radius: 12px; background-color: #1f1f1f; color: #f1f1f1;}
.user-message {background-color: #4caf50; color: white; padding: 10px; border-radius: 10px;
    margin: 8px 0; max-width: 75%; float: right; clear: both;}
.bot-message {background-color: #333; color: #f1f1f1; padding: 10px; border-radius: 10px;
    margin: 8px 0; max-width: 75%; float: left; clear: both;}
.clearfix {clear: both;}
</style>
""", unsafe_allow_html=True)

st.markdown("<h2 style='text-align: left; margin-top: 0;'>🤖 TalkTonic</h2>", unsafe_allow_html=True)

if st.button("🗑️ Clear Chat"):
    st.session_state.messages = []
    st.session_state.pending_input = ""
    st.session_state.last_file_hash = None
    st.session_state.extracted_text = ""

user_input = st.chat_input("Type your message...")
if user_input:
    input_text = user_input.strip()
    st.session_state.messages.append(("user", "text", input_text))
    typ = detect_input_type(input_text)

    try:
        

        if is_csv(user_input):
            try:
                
                df = pd.read_csv(io.StringIO(user_input))
                json_data = df.to_dict(orient="records")

        
                json_html = f"<pre>{json.dumps(json_data, indent=2)}</pre>"

      
                table_html = df.to_html(index=False, border=0)

       
                combined_html = f"<b>Detected JSON:</b><br>{json_html}<br><b>Detected Table:</b><br>{table_html}"

        
                st.session_state.messages.append(("bot", "text", combined_html))

            except Exception as e:
                st.session_state.messages.append(("bot", "text", f"[CSV parse error: {e}]"))



        elif is_url(user_input) or typ == "url":
            bot_reply = summarize_website(user_input)
            st.session_state.messages.append(("bot", "text", bot_reply))


        elif any(kw in input_text.lower() for kw in ["scrape", "summarize", "what's on", "get info","what is on"]) and re.search(r"https?://\S+", input_text):
            url_match = re.search(r"https?://\S+", input_text).group(0)
            bot_reply = summarize_website(url_match)
            st.session_state.messages.append(("bot", "text", bot_reply))




        else:
            llm_resp = call_groq_model(input_text)
            triggers = ["can't","not available","unable","sorry","hasn't","wasn't","As of","has not","clarify","As of"]
            if any(tok in llm_resp.lower() for tok in triggers):
                search_result = web_search_with_google_custom_search(input_text)
                st.session_state.messages.append(("bot", "text", f"{search_result}"))
            else:
                st.session_state.messages.append(("bot", "text", llm_resp))

    except Exception as e:
        st.session_state.messages.append(("bot", "text", f"[Internal routing error: {e}]"))


container_html = "<div class='chat-container'>"
for sender, payload_type, content in st.session_state.messages:
    if sender == "user":
        container_html += f"<div class='user-message'>{html.escape(str(content))}</div><div class='clearfix'></div>"
    else:
        if payload_type == "text":
       
            if str(content).strip().startswith("<b>Detected JSON"):
                container_html += f"<div class='bot-message'>{content}</div><div class='clearfix'></div>"
            else:
                safe_text = html.escape(str(content)).replace("\n", "<br>")
                container_html += f"<div class='bot-message'>{safe_text}</div><div class='clearfix'></div>"


container_html += "</div>"
st.markdown(container_html, unsafe_allow_html=True)


for sender, payload_type, content in st.session_state.messages:
    if sender == "bot" and payload_type == "table":
        try:
            import pandas as pd
            df = pd.DataFrame(content)
            st.markdown("**Detected CSV (rendered as table):**")
            st.dataframe(df)
        except Exception as e:
            st.text(f"[Could not render table: {e}]")
    if sender == "bot" and payload_type == "json":
        st.markdown("**Detected JSON:**")
        st.json(content)

st.markdown("""
<style>
.chat-container {
    height: 480px;
    overflow-y: auto;
    border: 1px solid #444;
    padding: 12px;
    border-radius: 12px;
    background-color: #1f1f1f;
    color: #f1f1f1;
}
.user-message, .bot-message {
    padding: 10px;
    border-radius: 10px;
    margin: 8px 0;
    max-width: 75%;
    word-wrap: break-word;
    overflow-wrap: anywhere;
    white-space: pre-wrap;
}
.user-message {
    background-color: #4caf50;
    color: white;
    float: right;
    clear: both;
}
.bot-message {
    background-color: #333;
    color: #f1f1f1;
    float: left;
    clear: both;
}
.clearfix { clear: both; }
</style>
""", unsafe_allow_html=True)

