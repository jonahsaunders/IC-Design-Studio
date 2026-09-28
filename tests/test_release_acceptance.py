import unittest
from icstudio.model import clone
from icstudio.release_acceptance import TASKS,blockers


class ConsumerAcceptanceTests(unittest.TestCase):
    def report(self):
        return dict(acceptance_schema=1,build=dict(frozen=True,dirty=False,commit='a'*40),
            package=dict(name='installer.exe',sha256='b'*64),host_class='consumer',
            consumer_platform='windows',environment_notes='Consumer laptop and two mixed-scale monitors',
            display='windows',screens=[dict(scale=1)],automated=dict(status='passed'),
            observations=[dict(id=key,status='Passed') for key in TASKS])

    def test_exact_packages_and_commit(self):
        report=self.report()
        self.assertEqual(blockers(report,'a'*40,'b'*64,'windows'),[])
        for args in [('c'*40,'b'*64,'windows'),('a'*40,'c'*64,'windows'),('a'*40,'b'*64,'ubuntu')]:
            self.assertTrue(blockers(report,*args))

    def test_no_partial_or_hosted_acceptance(self):
        base=self.report()
        for key,value in [('observations',base['observations'][:-1]),('host_class','hosted'),
                          ('display','offscreen'),('environment_notes',''),('screens',[]),
                          ('build',dict(frozen=False,dirty=False,commit='a'*40)),
                          ('automated',dict(status='failed')),('package',None)]:
            report=clone(base);report[key]=value
            with self.subTest(key=key):self.assertTrue(blockers(report))
        for status in ('Not run','Failed','Blocked'):
            report=clone(base);report['observations'][0]['status']=status
            self.assertTrue(blockers(report))
        report=clone(base);report['observations'][-1]=report['observations'][0]
        self.assertTrue(blockers(report))
        report=clone(base);report['consumer_platform']='ubuntu'
        self.assertTrue(blockers(report))
        report=clone(base);report['os']='Windows Server 2022'
        self.assertTrue(blockers(report))
