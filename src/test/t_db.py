# from datetime import datetime
# from typing import List
#
# from sqlalchemy import ForeignKey, String, DateTime, create_engine
# from sqlalchemy.orm import Session, DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
# from src.models import Category, TransactionType, Transaction, TransactionCategoryAssociation,User
# from src.db import init_db, engine
#
# # # 1. Очистити і створити таблиці заново
# # init_db()
# #
# # # 2. Відкрити сесію і додати тестові дані
# # with Session(engine) as session:
# #
# #     print("User is creating")
# #     user = User(username="testuser", email="test@example.com", hashed_password="hash")
# #     session.add(user)
# #     session.commit()
# #
# #     print("User was added")
# #
# #     tx = Transaction(
# #         type=TransactionType.income,
# #         amount=100,
# #         description="Test income",
# #         user=user
# #     )
# #     session.add(tx)
# #     session.commit()
# #
# #     # 3. Прочитати транзакцію назад і вивести
# #     tx_loaded = session.get(Transaction, tx.id)
# #     print(f"Transaction loaded: {tx_loaded.description}, amount: {tx_loaded.amount}")
#
#
# # # Базовий клас для моделей
# # class Base(DeclarativeBase):
# #     pass
# #
# # # Модель для асоціативної таблиці
# # class ExpenseCategory(Base):
# #     __tablename__ = 'expense_category'
# #
# #     expense_id: Mapped[int] = mapped_column(ForeignKey('expenses.id'), primary_key=True)
# #     category_id: Mapped[int] = mapped_column(ForeignKey('categories.id'), primary_key=True)
# #
# #     # Зв’язки до обох моделей
# #     expense: Mapped['Expense'] = relationship(back_populates='category_associations')
# #     category: Mapped['Category'] = relationship(back_populates='expense_associations')
# #
# #     # Додаткові атрибути (опціонально)
# #     # Наприклад, можна додати вагу категорії для витрати
# #     # weight: Mapped[float | None] = mapped_column(Float, nullable=True)
# #
# # # Модель для витрат/поповнень
# # class Expense(Base):
# #     __tablename__ = 'expenses'
# #
# #     id: Mapped[int] = mapped_column(primary_key=True)
# #     amount: Mapped[float] = mapped_column(nullable=False)
# #     description: Mapped[str] = mapped_column(String, nullable=True)
# #     date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
# #     type: Mapped[str] = mapped_column(String, nullable=False)  # 'expense' або 'income'
# #
# #     # Зв’язок до асоціативної таблиці
# #     category_associations: Mapped[List['ExpenseCategory']] = relationship(
# #         back_populates='expense',
# #         cascade='all, delete-orphan'
# #     )
# #
# #     # Допоміжний зв’язок для прямого доступу до категорій
# #     categories: Mapped[List['Category']] = relationship(
# #         secondary='expense_category',
# #         viewonly=True
# #     )
# #
# # # Модель для категорій
# # class Category(Base):
# #     __tablename__ = 'categories'
# #
# #     id: Mapped[int] = mapped_column(primary_key=True)
# #     name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
# #
# #     # Зв’язок до асоціативної таблиці
# #     expense_associations: Mapped[List['ExpenseCategory']] = relationship(
# #         back_populates='category',
# #         cascade='all, delete-orphan'
# #     )
# #
# #     # Допоміжний зв’язок для прямого доступу до витрат
# #     expenses: Mapped[List['Expense']] = relationship(
# #         secondary='expense_category',
# #         viewonly=True
# #     )
# #
# # # Створення бази даних
# # engine = create_engine('sqlite:///expenses.db', echo=True)
# # Base.metadata.create_all(engine)
#
# # Створення сесії
# Session = sessionmaker(bind=engine)
#
# # Приклад використання
# def main():
#     with Session() as session:
#
#         user = User(username="shadoww", email="shadoww@gmail.com", hashed_password="<1234567890")
#
#         session.add(user)
#         session.commit()
#
#         # Створення категорій
#         food = Category(name='Їжа')
#         entertainment = Category(name='Розваги')
#         session.add_all([food, entertainment])
#         session.commit()
#
#         # Створення витрати
#         expense = Transaction(
#             amount=50.0,
#             description='Вечеря в ресторані',
#             type=TransactionType.expense,
#             owner=user,
#         )
#
#         # Додавання зв’язків через асоціативну модель
#         expense.categories_associations = [
#             TransactionCategoryAssociation(category=food),
#             TransactionCategoryAssociation(category=entertainment)
#         ]
#
#         session.add(expense)
#         session.commit()
#
#         expense2 = Transaction(
#             amount=155.0,
#             description="Поїздка в Львів",
#             type=TransactionType.expense,
#             owner=user,
#         )
#
#         session.add(expense2)
#         session.commit()
#
#         session.refresh(user)
#
#         for t in user.transactions:
#             print(t)
#
#         # Запит витрат із категоріями
#         expenses = session.query(Transaction).all()
#
#         category = Category(
#             name="Не потрібна витрата"
#         )
#
#         session.add(category)
#         session.commit()
#
#         for expense in expenses:
#             expense.categories_associations.append(TransactionCategoryAssociation(category=category))
#             session.add(expense)
#             session.commit()
#
#         income = Transaction(
#             amount=210.0,
#             type=TransactionType.income,
#             description="Отримання грошей з картки",
#             owner=user
#         )
#
#         income.categories_associations = [TransactionCategoryAssociation(category=Category(name="Ура нові гроші!!!"))]
#
#         session.add(income)
#         session.commit()
#
#         for expense in expenses:
#             categories = [assoc.category.name for assoc in expense.categories_associations]
#             print(f"Витрата: {expense.description}, Сума: {expense.amount}, Категорії: {categories}")
#
#         expenses = session.query(Transaction).filter(Transaction.type == TransactionType.expense).all()
#
#         print(expenses)
#
#         incomes = session.query(Transaction).filter(Transaction.type == TransactionType.income).all()
#         for income in incomes:
#             categories = [assoc.category.name for assoc in income.categories_associations]
#             print(f"Поповнення: {income.description}, Сума: {income.amount}, Категорії: {categories}")
#
# if __name__ == '__main__':
#     main()