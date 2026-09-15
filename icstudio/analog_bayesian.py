"""Bounded constrained expected-hypervolume proposals, using measured evidence.

Separate fitted Matérn GPs describe each objective and the most limiting signed
constraints. Predictions propose simulations; they are not pass/yield evidence.
No machine-learning runtime or installation step is required.
"""
import math
import random
import statistics


def kernel(a, b, lengths):
    r = math.sqrt(sum(((x-y)/l)**2 for x,y,l in zip(a,b,lengths)))
    return (1+math.sqrt(5)*r+5*r*r/3)*math.exp(-math.sqrt(5)*r)


def solve(lower, rhs):
    y=[]
    for i,row in enumerate(lower):y.append((rhs[i]-sum(row[j]*y[j] for j in range(i)))/row[i])
    x=[0.]*len(y)
    for i in reversed(range(len(y))):x[i]=(y[i]-sum(lower[j][i]*x[j] for j in range(i+1,len(y))))/lower[i][i]
    return x


class FittedGP:
    def __init__(self, x, y):
        self.x=x; self.mean=statistics.fmean(y); self.scale=max(statistics.pstdev(y),abs(self.mean)*1e-9,1e-300)
        normalized=[(v-self.mean)/self.scale for v in y]
        def fit(lengths):
            n=len(x); lower=[[0.]*n for _ in x]
            for i in range(n):
                for j in range(i+1):
                    value=kernel(x[i],x[j],lengths)+(1e-6 if i==j else 0)-sum(lower[i][k]*lower[j][k] for k in range(j))
                    if i==j and value<=0:raise ValueError('The surrogate covariance could not be factored.')
                    lower[i][j]=math.sqrt(value) if i==j else value/lower[j][j]
            alpha=solve(lower,normalized)
            likelihood=-.5*sum(v*a for v,a in zip(normalized,alpha))-sum(math.log(lower[i][i]) for i in range(n))
            return likelihood,lower,alpha
        choices=[([v]*len(x[0])) for v in (.15,.4,1.2)]
        lengths=max(choices,key=lambda v:fit(v)[0])
        # One bounded coordinate pass learns unequal parameter length scales.
        for axis in range(len(lengths)):
            choices=[lengths[:axis]+[v]+lengths[axis+1:] for v in (.15,.4,1.2)]
            lengths=max(choices,key=lambda v:fit(v)[0])
        _,self.lower,self.alpha=fit(lengths);self.lengths=lengths

    def predict(self, point):
        k=[kernel(point,x,self.lengths) for x in self.x]; weights=solve(self.lower,k)
        return (self.mean+self.scale*sum(a*b for a,b in zip(k,self.alpha)),
                self.scale*math.sqrt(max(1e-12,1-sum(a*b for a,b in zip(k,weights)))))


def front(points):
    points=list(dict.fromkeys(tuple(p) for p in points))
    return [p for p in points if not any(all(a<=b for a,b in zip(q,p)) and q!=p for q in points)]


def hypervolume(points, reference):
    """Exact union of dominated boxes, for one to three minimized objectives."""
    points=[tuple(p) for p in points if all(a<b for a,b in zip(p,reference))]
    if not points:return 0.
    if len(reference)==1:return reference[0]-min(p[0] for p in points)
    if len(reference)==2:
        ordered=sorted(points);area=0.;low=reference[1]
        for i,p in enumerate(ordered):
            low=min(low,p[1]);right=ordered[i+1][0] if i+1<len(ordered) else reference[0]
            area+=(right-p[0])*(reference[1]-low)
        return area
    edges=sorted({p[0] for p in points}|{reference[0]})
    return sum((b-a)*hypervolume([p[1:] for p in points if p[0]<=a],reference[1:]) for a,b in zip(edges,edges[1:]))


def cdf(value):return .5*(1+math.erf(value/math.sqrt(2)))


def propose(manifest, report, grids):
    state=manifest['adaptive']; coordinates=state['coordinates']; sizes=list(map(len,grids))
    feature=lambda c:[v/(n-1) for v,n in zip(c,sizes)]
    measured=[c for c in report['candidates'] if c['complete']==c['total'] and not c.get('evidence_errors')
              and all(m['score'] is not None for m in c['metrics'])]
    if len(measured)<3:return None
    rng=random.Random(18181+state['batches']); measured=sorted(measured,key=lambda c:(not c['pareto'],c['candidate']))
    if len(measured)>32:measured=measured[:12]+rng.sample(measured[12:],20)
    x=[feature(coordinates[c['candidate']-1]) for c in measured]
    objectives=[FittedGP(x,[c['metrics'][i]['score'] for c in measured]) for i in range(len(measured[0]['metrics']))]
    keys=set.intersection(*(set(c.get('constraints',{})) for c in measured))
    keys=sorted(keys,key=lambda key:max(c['constraints'][key] for c in measured),reverse=True)[:6]
    constraints=[FittedGP(x,[c['constraints'][key] for c in measured]) for key in keys]
    bounds=[(min(c['metrics'][i]['score'] for c in measured),max(c['metrics'][i]['score'] for c in measured)) for i in range(len(objectives))]
    normalize=lambda values:[(v-lo)/max(hi-lo,abs(lo)*.01,1e-30) for v,(lo,hi) in zip(values,bounds)]
    observed=front([normalize([m['score'] for m in c['metrics']]) for c in measured if c['state']=='Passed'])
    reference=[1.2]*len(objectives); before=hypervolume(observed,reference)
    seen=set(map(tuple,coordinates)); pool=set()
    for _ in range(256):
        point=tuple(rng.randrange(n) for n in sizes)
        if point not in seen:pool.add(point)
        if len(pool)>=48:break
    for c in measured[:8]:
        point=coordinates[c['candidate']-1]
        for i,n in enumerate(sizes):
            for shift in (-1,1):
                p=tuple(point[:i]+[max(0,min(n-1,point[i]+shift))]+point[i+1:])
                if p not in seen:pool.add(p)
    pool=sorted(pool)[:96]
    if not pool:return None
    normal_draws=[[rng.gauss(0,1) for _ in objectives] for _ in range(12)]
    proposals=[]
    settled={c['candidate'] for c in report['candidates'] if c['complete']==c['total'] or c['state']!='Pending'}
    pending=[feature(p) for i,p in enumerate(coordinates,1) if i not in settled]
    for point in pool:
        f=feature(point); predicted=[g.predict(f) for g in objectives]; limits=[g.predict(f) for g in constraints]
        probability=math.prod(cdf(-mu/max(sd,1e-12)) for mu,sd in limits)
        if not observed:
            score=-sum(max(mu,0) for mu,sd in limits)+.05*sum(sd for mu,sd in limits)
            if not limits:score=-sum(normalize([mu for mu,sd in predicted]))
        else:
            gain=statistics.fmean(max(0,hypervolume(observed+[normalize([mu+z*sd for (mu,sd),z in zip(predicted,draw)])],reference)-before) for draw in normal_draws)
            score=gain*max(probability,.01)
        # Pending members of a parallel batch receive a distance penalty.
        distance=min((math.sqrt(sum((a-b)**2 for a,b in zip(f,p))) for p in pending),default=1.)
        score-=max(0,.1-distance)*.01
        proposals.append((score,point,predicted,probability))
    score,point,predicted,probability=max(proposals,key=lambda p:(p[0],p[1]))
    state['proposal_evidence']=dict(method='Constrained expected hypervolume improvement' if observed else 'Feasibility-first constrained search',
        score_means=[p[0] for p in predicted], score_standard_deviations=[p[1] for p in predicted],
        modeled_constraint_probability=probability, modeled_constraints=keys, observations=len(measured),
        length_scales=[g.lengths for g in objectives], acquisition=score,
        note='Model estimates only, not verified performance or manufacturing yield. Scores are the value when minimizing, its negative when maximizing, or absolute target error. Every required condition is still simulated.')
    return list(point)
