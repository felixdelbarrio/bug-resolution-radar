"""HTTP contract for the local Contact Center PYME configuration."""

from fastapi import APIRouter, HTTPException, Response

from bug_resolution_radar.config import load_settings
from bug_resolution_radar.services.contact_center_pyme import (
    ContactCenterConfig,
    ContactCenterPayload,
    ContactCenterStorageError,
    contact_center_pyme_payload,
    save_contact_center_pyme,
)

router = APIRouter(prefix="/api/contact-center-pyme", tags=["settings"])


@router.get("/{country}", response_model=ContactCenterPayload)
def get_contact_center_pyme(country: str, response: Response) -> ContactCenterPayload:
    response.headers["Cache-Control"] = "no-store"
    try:
        return contact_center_pyme_payload(load_settings(), country)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ContactCenterStorageError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/{country}", response_model=ContactCenterPayload)
def put_contact_center_pyme(
    country: str, payload: ContactCenterConfig, response: Response
) -> ContactCenterPayload:
    response.headers["Cache-Control"] = "no-store"
    try:
        return save_contact_center_pyme(load_settings(), country, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ContactCenterStorageError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
