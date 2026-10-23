import logging

def get_logger():
    return logging.getLogger(__name__)

def setup_logger():
    # See https://docs.python.org/3/howto/logging.html
    logger = get_logger()
    logger.setLevel(logging.DEBUG)

    # create console handler and set level to debug
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)

    # create formatter
    formatter = logging.Formatter('%(asctime)s.%(msecs)03d %(name)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')

    # add formatter to ch
    ch.setFormatter(formatter)

    # add ch to logger
    logger.addHandler(ch)

setup_logger()