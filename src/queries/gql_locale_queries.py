from typing import Tuple, Dict, Any

def get_locales(channel_id: int) -> Tuple[str, Dict[str, Any]]:
    query = """
    query GetLocales($channelId: ID!) {
      store {
        locales(input: { channelId: $channelId }) {
          edges {
            node {
              code
              status
              isDefault
            }
          }
        }
      }
    }
    """
    variables: Dict[str, Any] = {
        "channelId": f"bc/store/channel/{channel_id}"
    }
    return query, variables