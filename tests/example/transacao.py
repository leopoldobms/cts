import re

def validateTransaction (requestTransaction):
    if re.search('\\bvalor\\b', requestTransaction, re.IGNORECASE):
        return True
    else:
        return False
    


