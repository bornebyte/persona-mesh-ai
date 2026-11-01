import requests
import os

# 1. Configuration
# API_URL = "https://gql.hashnode.com/"
API_URL = "https://gql-beta.hashnode.com/"
PERSONAL_ACCESS_TOKEN = os.getenv("HASHNODE_API_KEY")
PUBLICATION_ID = "YOUR_PUBLICATION_ID"

# 2. Define the GraphQL Mutation
# This mutation targets the 'publishPost' endpoint
publish_mutation = """
mutation PublishPost($input: PublishPostInput!) {
  publishPost(input: $input) {
    post {
      id
      slug
      url
    }
  }
}
"""

# 3. Setup the payload variables
variables = {
    "input": {
        "publicationId": PUBLICATION_ID,
        "title": "Automating Hashnode Posts with Python",
        "contentMarkdown": "## Hello World\n\nThis post was published completely using a **Python** script!",
        "tags": [
            {"id": "56744721958ef13879b94c7e", "slug": "python", "name": "Python"}
        ]
    }
}

# 4. Configure headers
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {PERSONAL_ACCESS_TOKEN}"
}
# 5. Execute the POST request
try:
    response = requests.post(
        API_URL, 
        json={"query": publish_mutation, "variables": variables}, 
        headers=headers
    )
    
    # Let's inspect what Hashnode actually sent back before parsing JSON
    print(f"Status Code: {response.status_code}")
    print(f"Raw Response Content:\n{response.text[:500]}") # Shows first 500 characters
    
    response.raise_for_status()
    result = response.json()
    
    if "errors" in result:
        print("GraphQL Errors:", result["errors"])
    else:
        post_info = result["data"]["publishPost"]["post"]
        print("🎉 Post published successfully!")
        print(f"URL: {post_info['url']}")

except requests.exceptions.HTTPError as http_err:
    print(f"HTTP error occurred: {http_err}")
except Exception as err:
    print(f"An error occurred parsing JSON: {err}")
