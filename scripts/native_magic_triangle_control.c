/* Private fixture inserted only into isolated qualification builds. */
extern TileTypeBitMask ResNoMergeMask[NT];
static resNode *newnode(int id) {
    resNode *n=(resNode *)mallocMagic(sizeof(resNode));
    InitializeResNode(n,id*10,id*20,RES_NODE_ORIGIN);
    return n;
}
static resResistor *edge(resNode *a,resNode *b,float value) {
    resResistor *r=(resResistor *)mallocMagic(sizeof(resResistor));memset(r,0,sizeof(*r));
    r->rr_connection1=a;r->rr_connection2=b;r->rr_value=value;r->rr_tt=0;
    resNode *ends[2]={a,b};
    for(int i=0;i<2;i++) {resElement *e=(resElement *)mallocMagic(sizeof(resElement));e->re_thisEl=r;e->re_nextEl=ends[i]->rn_re;ends[i]->rn_re=e;}
    return r;
}
static void icstudioTriangleControl(TxCommand *cmd) {
    int degree;double input[3];char result[2048];
    degree=atoi(cmd->tx_argv[2]);
    if(degree<2 || degree>20) {TxPrintf("TRIANGLE_ERROR degree\n");return;}
    for(int i=0;i<3;i++) {input[i]=strtod(cmd->tx_argv[i+3],NULL);if(!isfinite(input[i]) || input[i]<=0) {TxPrintf("TRIANGLE_ERROR value\n");return;}}
    ResNodeList=NULL;ResNodeQueue=NULL;ResResList=NULL;ResOptionsFlags=0;TTMaskZero(&ResNoMergeMask[0]);
    resNode *a=newnode(0),*b=newnode(1),*c=newnode(2);
    resResistor *ab=edge(a,b,(float)input[0]),*ac=edge(a,c,(float)input[1]),*bc=edge(b,c,(float)input[2]);
    double actual[3]={ab->rr_value,ac->rr_value,bc->rr_value};
    for(int i=2;i<degree;i++)edge(a,newnode(i+1),1000+i);
    int status=ResTriangleCheck(a);
    resNode *center=ResNodeList;double arms[3]={-1,-1,-1};int count=0;resNode *ends[3]={a,b,c};
    if(center)for(resElement *e=center->rn_re;e;e=e->re_nextEl){resResistor *r=e->re_thisEl;resNode *other=r->rr_connection1==center?r->rr_connection2:r->rr_connection1;for(int i=0;i<3;i++)if(other==ends[i])arms[i]=r->rr_value;count++;}
    snprintf(result,sizeof(result),"{\"status\":%d,\"triangle_status\":%d,\"degree\":%d,\"star_degree\":%d,\"input_milliohm\":[%.17g,%.17g,%.17g],\"arms_milliohm\":[%.17g,%.17g,%.17g]}",status,TRIANGLE,degree,count,actual[0],actual[1],actual[2],arms[0],arms[1],arms[2]);
    TxPrintf("TRIANGLE_RESULT %s\n",result);return;
}
