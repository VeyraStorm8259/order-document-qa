from fastapi import FastAPI, HTTPException

from .infrai_client import InfraiClient, InfraiError
from .order_questions import QuestionRequest, QuestionResponse, answer_order_question


app = FastAPI(title="Order document questions")


@app.post("/questions", response_model=QuestionResponse)
def ask_question(request: QuestionRequest) -> QuestionResponse:
    try:
        return answer_order_question(request, InfraiClient())
    except InfraiError as exc:
        status_code = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(status_code=status_code, detail={"code": exc.code, "message": str(exc)}) from exc
