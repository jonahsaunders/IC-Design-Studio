#include <algorithm>
#include <cmath>
#include <vector>
#ifdef _WIN32
#define API extern "C" __declspec(dllexport)
#else
#define API extern "C" __attribute__((visibility("default")))
#endif
// Dense pivoted Gaussian elimination. Returns 0 on success, 1 on invalid/singular input.
API int ic_solve(int n, const double* matrix, const double* rhs, double* result) {
    if(n<1 || n>256 || !matrix || !rhs || !result) return 1;
    std::vector<double> a(matrix,matrix+n*n), b(rhs,rhs+n);
    for (int k=0;k<n;++k) {
        int p=k;
        for(int i=k+1;i<n;++i) if(std::abs(a[i*n+k])>std::abs(a[p*n+k])) p=i;
        if(!std::isfinite(a[p*n+k]) || std::abs(a[p*n+k])<1e-24) return 1;
        if(p!=k) {for(int j=k;j<n;++j) std::swap(a[k*n+j],a[p*n+j]); std::swap(b[k],b[p]);}
        for(int i=k+1;i<n;++i) {
            double f=a[i*n+k]/a[k*n+k];
            for(int j=k+1;j<n;++j) a[i*n+j]-=f*a[k*n+j];
            b[i]-=f*b[k];
        }
    }
    for(int i=n-1;i>=0;--i) {
        double s=b[i]; for(int j=i+1;j<n;++j) s-=a[i*n+j]*result[j];
        result[i]=s/a[i*n+i]; if(!std::isfinite(result[i])) return 1;
    }
    return 0;
}
