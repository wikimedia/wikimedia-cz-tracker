from crequest.middleware import CrequestMiddleware


def get_request():
    return CrequestMiddleware.get_request()
