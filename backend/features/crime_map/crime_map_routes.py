from fastapi import APIRouter, Depends
from features.crime_map.crime_map_controller import (
    get_boundaries,
    get_pins,
    get_statistics,
    get_heatmap,
)
from shared.middleware.token_middleware import authenticate

router = APIRouter()

@router.get("/boundaries")
async def boundaries(user=Depends(authenticate)):
    return await get_boundaries(user)

@router.get("/pins")
async def pins(user=Depends(authenticate)):
    return await get_pins(user)

@router.get("/statistics")
async def statistics(user=Depends(authenticate)):
    return await get_statistics(user)

@router.get("/heatmap")
async def heatmap(user=Depends(authenticate)):
    return await get_heatmap(user)