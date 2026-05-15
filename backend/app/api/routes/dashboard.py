from fastapi import APIRouter

from app.services.mock_data import store

router = APIRouter()


@router.get("")
def get_dashboard():
    return store.build_dashboard()
