from playwright.async_api import Page
import json

class APIInterceptor:
    @staticmethod
    async def intercept_api_calls(page: Page) -> dict:
        """
        Intercept XHR/fetch calls and return the most data-heavy endpoint.
        """
        api_calls = {}
        
        def handle_response(response):
            url = response.url
            if any(x in url for x in ["api", "graphql", "/data", "/json"]):
                api_calls[url] = {
                    "status": response.status,
                    "headers": dict(response.headers)
                }
        
        page.on("response", handle_response)
        await page.wait_for_timeout(3000)  # Wait for API calls
        page.remove_listener("response", handle_response)
        
        return api_calls

    @staticmethod
    def generate_requests_script(endpoint: str, params: dict = None) -> str:
        return f'''
import requests
import json

url = "{endpoint}"
params = {json.dumps(params or {})}
headers = {{"User-Agent": "Mozilla/5.0"}}

response = requests.get(url, params=params, headers=headers)
data = response.json()

# Save data
with open("data/api_data.json", "w") as f:
    json.dump(data, f, indent=2)

print(f"Saved {{len(data)}} items from API")
'''