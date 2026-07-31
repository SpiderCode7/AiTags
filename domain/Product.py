from sqlmodel import Field, Session, SQLModel, create_engine, select

class Product(SQLModel, table=True):
    __tablename__ = "products"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    ai_tags: str | None = None