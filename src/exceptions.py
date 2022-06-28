from fastapi import Response

class Unauthorized(Exception):
    def __init__(self, response: Response, *args: object) -> None:
        self.response = response
        super().__init__(*args)


class RefreshDatabaseError(Exception):
    pass