import os

import uvicorn
from fastapi import FastAPI
from app.api.v1.endpoints import auth, users, categories, currencies, transactions
app = FastAPI(title="Finance Tracker API", version="1.0.0")


app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(categories.router, prefix="/api/v1")
app.include_router(currencies.router, prefix="/api/v1")
app.include_router(transactions.router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"message": "Finance Tracker API"}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True, reload_dirs=[os.path.abspath("app")])
    # uvicorn.run("app.main:app", host="0.0.0.0", port=8020, reload=False)

# test user
# {
#   "username": "user1234",
#   "email": "testuser1234@gmail.com",
#   "password": "qWerty12#"
# }