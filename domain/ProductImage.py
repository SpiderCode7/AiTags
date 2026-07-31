from sqlmodel import Field, SQLModel

class ProductImage(SQLModel, table=True):
    __tablename__ = "product_image"

    id: int | None = Field(default=None, primary_key=True)
    product_id: int
    image_url: str
    image_type: int