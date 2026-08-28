from pydantic import BaseModel, Field


class RefundRequest(BaseModel):
    payment_id: str
    amount_paise: int = Field(gt=0)