import asyncio
from form_parser import extract_semantic_dom
from page_loader import load_page_html

URL = "https://jobs.lever.co/palantir/94984771-0704-446c-88c6-91ce748f6d92?utm_campaign=google_jobs_apply&utm_source=google_jobs_apply&utm_medium=organic"

async def main():
    html = await load_page_html(URL)
    dom = extract_semantic_dom(html)
    print(dom)

if __name__ == "__main__":
    asyncio.run(main())