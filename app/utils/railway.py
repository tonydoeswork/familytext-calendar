import logging
import os

import httpx

logger = logging.getLogger(__name__)

_RAILWAY_GQL = 'https://backboard.railway.app/graphql/v2'

_UPSERT = """
mutation variableUpsert($input: VariableUpsertInput!) {
    variableUpsert(input: $input)
}
"""


def update_variable(name: str, value: str) -> bool:
    """Update a Railway environment variable via the Railway API.

    Requires four env vars to be set:
        RAILWAY_API_TOKEN, RAILWAY_PROJECT_ID,
        RAILWAY_SERVICE_ID, RAILWAY_ENVIRONMENT_ID

    If any are missing the call is skipped and False is returned.
    """
    token = os.environ.get('RAILWAY_API_TOKEN')
    project_id = os.environ.get('RAILWAY_PROJECT_ID')
    service_id = os.environ.get('RAILWAY_SERVICE_ID')
    environment_id = os.environ.get('RAILWAY_ENVIRONMENT_ID')

    if not all([token, project_id, service_id, environment_id]):
        logger.warning(
            'Railway auto-update skipped — RAILWAY_API_TOKEN / RAILWAY_PROJECT_ID / '
            'RAILWAY_SERVICE_ID / RAILWAY_ENVIRONMENT_ID not all set'
        )
        return False

    try:
        resp = httpx.post(
            _RAILWAY_GQL,
            json={
                'query': _UPSERT,
                'variables': {
                    'input': {
                        'projectId': project_id,
                        'environmentId': environment_id,
                        'serviceId': service_id,
                        'name': name,
                        'value': value,
                    }
                },
            },
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
            },
            timeout=10,
        )
        data = resp.json()
        if 'errors' in data:
            logger.error(f'Railway API error updating {name}: {data["errors"]}')
            return False
        logger.info(f'Railway variable {name} auto-updated successfully')
        return True
    except Exception as exc:
        logger.error(f'Failed to update Railway variable {name}: {exc}')
        return False
