# import enum
# from datetime import datetime
#
# from sqlalchemy import (
#     Column, Integer, String, Float, DateTime, ForeignKey, Enum, Table
# )
# from sqlalchemy.orm import relationship
#
# from src.db.database import Base
#
#
# # Тип транзакції: дохід або витрата
# class TransactionType(enum.Enum):
#     income = "income"
#     expense = "expense"
#
# # Зв’язок багато-до-багатьох: транзакції ↔ категорії
# transaction_categories = Table(
#     "transaction_categories",
#     Base.metadata,
#     Column("transaction_id", Integer, ForeignKey("transactions.id", ondelete="CASCADE"), primary_key=True),
#     Column("category_id", Integer, ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True)
# )
#
# # Користувачі
# class User(Base):
#     __tablename__ = "users"
#
#     id = Column(Integer, primary_key=True)
#     username = Column(String, unique=True, nullable=False)
#     email = Column(String, unique=True)
#     password_hash = Column(String, nullable=False)
#     created_at = Column(DateTime, default=datetime.utcnow)
#
#     transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
#     categories = relationship("Category", back_populates="user", cascade="all, delete-orphan")
#
# # Категорії (одна категорія може належати одному користувачу)
# class Category(Base):
#     __tablename__ = "categories"
#
#     id = Column(Integer, primary_key=True)
#     name = Column(String, nullable=False)
#     user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
#
#     user = relationship("User", back_populates="categories")
#     transactions = relationship("Transaction", secondary=transaction_categories, back_populates="categories")
#
# # Транзакції
# class Transaction(Base):
#     __tablename__ = "transactions"
#
#     id = Column(Integer, primary_key=True)
#     user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
#     type = Column(Enum(TransactionType), nullable=False)  # 'income' або 'expense'
#     amount = Column(Float, nullable=False)               # сума
#     quantity = Column(Float, nullable=True)              # кількість товару
#     unit = Column(String, nullable=True)                 # одиниця виміру, напр. 'шт', 'кг'
#     description = Column(String, nullable=True)
#     date = Column(DateTime, default=datetime.utcnow)
#
#     user = relationship("User", back_populates="transactions")
#     categories = relationship("Category", secondary=transaction_categories, back_populates="transactions")
