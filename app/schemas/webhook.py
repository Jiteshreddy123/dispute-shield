from pydantic import BaseModel


class AcquirerData(BaseModel):
    arn: str | None = None


class RefundEntity(BaseModel):
    id: str
    amount: int
    payment_id: str
    status: str
    acquirer_data: AcquirerData | None = None


class RefundObject(BaseModel):
    entity: RefundEntity


class WebhookPayload(BaseModel):
    refund: RefundObject


class RazorpayWebhook(BaseModel):
    event: str
    payload: WebhookPayload

class DisputeEntity(BaseModel):
    id: str
    payment_id: str
    amount: int
    status: str
    phase: str
    reason_code: str | None = None


class DisputeObject(BaseModel):
    entity: DisputeEntity


class PaymentEntity(BaseModel):
    id: str
    amount: int
    currency: str
    status: str


class PaymentObject(BaseModel):
    entity: PaymentEntity


class DisputeWebhookPayload(BaseModel):
    payment: PaymentObject
    dispute: DisputeObject


class RazorpayDisputeWebhook(BaseModel):
    event: str
    payload: DisputeWebhookPayload

