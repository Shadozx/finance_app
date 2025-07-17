import logging
import os

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.exceptions import EntityNotFoundException
from src.routes import category_router, transaction_router, user_router, unit_router

# Налаштування логера для Uvicorn
# logging.getLogger("uvicorn").setLevel(logging.CRITICAL)
logging.getLogger("uvicorn.error").setLevel(logging.CRITICAL)
# logging.getLogger("uvicorn.access").setLevel(logging.CRITICAL)

app = FastAPI(title="Finance App")


# Глобальний обробник для всіх винятків, що є спадкоємцями Exception
@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "message": "Виникла помилка на сервері",
            "detail": str(exc)
        }
    )


@app.exception_handler(EntityNotFoundException)
async def entity_not_found_exception_handler(request, exc: EntityNotFoundException):
    return JSONResponse(
        status_code=404,
        content={
            "message": exc.message,
            "detail": str(exc)
        }
    )


# Підключення роутерів
app.include_router(category_router)
app.include_router(transaction_router)
app.include_router(user_router)
app.include_router(unit_router)


@app.get("/")
async def root():
    return {"message": "Welcome to Finance App!"}


if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True, reload_dirs=[os.path.abspath("src")])
    # uvicorn.run("src.main:app", host="0.0.0.0", port=8020, reload=False)

'''
на даний момент, що буде вміти робити програма
*  користувач зайшов в систему
*  додає нову транзакцію(поповнення чи витрата), 
*        якщо витрата то можна описати що це за витрата, дату здійснення, може обрати одиницю витрати, штука, грам, кілограм і так далі.
*        якщо поповнення то теж пише дату отримання, опис щоб легко потім можна було відслідковувати витрати та поповнення.
*  потім вибирає категорії витрати, може також створити нові категорії. якщо витрата не підходить її можна редагувати чи видалити.
*  також фільтрувати по заданим датам транзакції.
'''
