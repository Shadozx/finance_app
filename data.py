# from src.db.database import SessionLocal, init_db
# from src.models.models import User, Category, Transaction, TransactionType
#
#
# def save():
#     session = SessionLocal()
#
#     # Створення користувача
#     user = User(username="roman", email="roman@example.com", password_hash="hash")
#     session.add(user)
#     session.commit()
#
#     # Створення категорій
#     food = Category(name="Продукти", user_id=user.id)
#     transport = Category(name="Транспорт", user_id=user.id)
#     session.add_all([food, transport])
#     session.commit()
#
#     # Створення транзакції
#     tx = Transaction(
#         user_id=user.id,
#         type=TransactionType.expense,
#         amount=89.0,
#         quantity=2,
#         unit="шт",
#         description="Макарони",
#         categories=[food]
#     )
#     session.add(tx)
#     session.commit()
#
#
# if __name__ == "__main__":
#     init_db()
#
#     session = SessionLocal()
#
#     existing_user = session.query(User).filter_by(email="roman@example.com").first()
#
#
#
#     # save()
#
#
