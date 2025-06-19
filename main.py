from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    """
    Handles GET requests to the root endpoint.

    Returns:
        dict: A dictionary containing a greeting message.
    """

    return {"message": "Hello World"}


def main():
    """
    main test Document

    
    """
    print("Hello from test!")


if __name__ == "__main__":
    main()
