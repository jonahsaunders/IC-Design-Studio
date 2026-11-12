import json,hashlib,unittest
from scripts.check_ihp_wsl_preparation_request import validate,BRANCH
class Request(unittest.TestCase):
 def test_exact_request_and_rejections(self):
  policy=json.dumps({'review_state':'APPROVED_FOR_BUILD_ONLY'}).encode();request={'schema':1,'purpose':'BUILD_PREPARATION_ONLY','native_execution':False,'request_id':'new-source-reviewed','policy_sha256':hashlib.sha256(policy).hexdigest()};sha='a'*40
  self.assertFalse(validate('push',BRANCH,sha,sha,request,policy)['native_execution'])
  for event,ref,expected,actual in [('pull_request',BRANCH,sha,sha),('push','refs/heads/main',sha,sha),('push',BRANCH,sha,'b'*40)]:
   with self.assertRaises(ValueError):validate(event,ref,expected,actual,request,policy)
  for field,value in [('native_execution',True),('purpose','RUN_PMOS'),('policy_sha256','0'*64),('request_id','../bad')]:
   with self.assertRaises(ValueError):validate('push',BRANCH,sha,sha,dict(request,**{field:value}),policy)
if __name__=='__main__':unittest.main()
