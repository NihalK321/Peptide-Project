import json
from .core import exact_reference, chemistry_quadratic
if __name__=='__main__':
    result=exact_reference()
    result['chemistry_quadratic']=chemistry_quadratic()
    print(json.dumps(result,indent=2))
