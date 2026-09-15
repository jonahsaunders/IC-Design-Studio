"""Optional, bounded Gaussian-process proposals with no extra installation.

Fixed RBF kernel, normalized grid coordinates, rotating scalarized objectives,
and a Gaussian feasibility surrogate. Acquisition scores guide simulations;
they are never performance/yield evidence. At most 64 training points and 256
proposals keep the desktop responsive. This is an experimental search backend.
"""
import math
import random


def kernel(a,b):
    return math.exp(-sum((x-y)**2 for x,y in zip(a,b))/(2*.3**2))


def forward(matrix,vector):
    out=[]
    for i,row in enumerate(matrix):out.append((vector[i]-sum(row[j]*out[j] for j in range(i)))/row[i])
    return out


class GaussianProcess:
    def __init__(self,x,y):
        self.x=x;self.mean=sum(y)/len(y)
        self.scale=max((sum((v-self.mean)**2 for v in y)/len(y))**.5,1e-9)
        n=len(x);self.lower=[[0.]*n for _ in x]
        for i in range(n):
            for j in range(i+1):
                value=kernel(x[i],x[j])+(1e-5 if i==j else 0)-sum(self.lower[i][k]*self.lower[j][k] for k in range(j))
                self.lower[i][j]=math.sqrt(max(value,1e-12)) if i==j else value/self.lower[j][j]
        rhs=forward(self.lower,[(v-self.mean)/self.scale for v in y]);self.alpha=[0.]*n
        for i in reversed(range(n)):
            self.alpha[i]=(rhs[i]-sum(self.lower[j][i]*self.alpha[j] for j in range(i+1,n)))/self.lower[i][i]

    def predict(self,x):
        covariance=[kernel(x,p) for p in self.x];v=forward(self.lower,covariance)
        return (self.mean+self.scale*sum(a*b for a,b in zip(covariance,self.alpha)),
                self.scale*math.sqrt(max(1e-12,1-sum(a*a for a in v))))


def cdf(x):return .5*(1+math.erf(x/math.sqrt(2)))


def propose(manifest,report,grids):
    state=manifest['adaptive'];coordinates=state['coordinates'];sizes=[len(g) for g in grids]
    feature=lambda p:[v/(n-1) for v,n in zip(p,sizes)]
    observed=[c for c in report['candidates'] if c['state'] in ('Passed','Failed','Screened out')]
    measured=[c for c in observed if c['metrics'] and all(m['score'] is not None for m in c['metrics'])]
    if len(measured)<3:return None
    rng=random.Random(7193+state['batches'])
    # Preserve extremes/Pareto evidence and spread the remaining training sample.
    measured=sorted(measured,key=lambda c:(not c['pareto'],c['candidate']))
    if len(measured)>64:measured=measured[:24]+rng.sample(measured[24:],40)
    ranges=[(min(c['metrics'][i]['score'] for c in measured),max(c['metrics'][i]['score'] for c in measured)) for i in range(len(measured[0]['metrics']))]
    weights=[rng.uniform(.1,1) for _ in ranges];total=sum(weights);weights=[w/total for w in weights]
    score=lambda c:sum(w*(m['score']-lo)/max(hi-lo,1e-12) for w,m,(lo,hi) in zip(weights,c['metrics'],ranges))
    gp=GaussianProcess([feature(coordinates[c['candidate']-1]) for c in measured],[score(c) for c in measured])
    feasible=[score(c) for c in measured if c['state']=='Passed'];best=min(feasible) if feasible else min(map(score,measured))
    labels=observed if len(observed)<=64 else rng.sample(observed,64)
    feasibility=GaussianProcess([feature(coordinates[c['candidate']-1]) for c in labels],[1. if c['state']=='Passed' else 0. for c in labels]) if len({c['state']=='Passed' for c in labels})>1 else None
    seen={tuple(c) for c in coordinates};pool=set()
    for _ in range(512):
        point=tuple(rng.randrange(n) for n in sizes)
        if point not in seen:pool.add(point)
        if len(pool)>=192:break
    for c in measured[:16]:
        center=coordinates[c['candidate']-1]
        for _ in range(4):
            point=tuple(max(0,min(n-1,v+rng.choice((-1,0,1)))) for v,n in zip(center,sizes))
            if point not in seen:pool.add(point)
    if not pool:return None
    def acquisition(point):
        x=feature(point);mean,sigma=gp.predict(x);improvement=best-mean;z=improvement/sigma
        ei=improvement*cdf(z)+sigma*math.exp(-z*z/2)/math.sqrt(2*math.pi)
        probability=1.
        if feasibility:
            mu,sd=feasibility.predict(x);probability=cdf((mu-.5)/max(sd,.05))
        # A small exploration floor prevents estimated infeasibility from
        # permanently excluding a region. It is not a calibrated probability.
        return (ei+.05*sigma)*max(.05,probability)
    return list(max(sorted(pool),key=acquisition))
