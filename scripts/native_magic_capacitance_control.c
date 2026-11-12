/* Qualification-only entry point; calls the actual parser and distributor. */
extern void ResDistributeCapacitance();
static void icstudioCapControl(TxCommand *cmd)
{
    int order=atoi(cmd->tx_argv[2]), exponent=atoi(cmd->tx_argv[3]);
    int mode=atoi(cmd->tx_argv[4]), count=4097;
    double scale=ldexp(1.0,exponent), distributed_sum=0;
    char value[80], result[2048];
    char *record[4]={"cap","ICSTUDIO_A","ICSTUDIO_B",value};
    if(order<0 || order>3 || exponent < -40 || exponent>40 || mode<0 || mode>1)
    {TxPrintf("CAP_ERROR arguments\n");return;}
    HashInit(&ResNodeTable,INITFLATSIZE,HT_STRINGKEYS);
    ResOriginalNodes=NULL;ResOptionsFlags=mode ? 0 : ResOpt_Signal;
    resNode *nodes=(resNode *)mallocMagic(count*sizeof(resNode));
    memset(nodes,0,count*sizeof(resNode));
    resNode *head=NULL,*previous=NULL;
    for(int i=0;i<count;i++)
    {
        int j=order==0 ? i : order==1 ? count-1-i : order==2 ? (i+2048)%count : (i*37)%count;
        snprintf(value,sizeof(value),"%.17g",ldexp(scale,j==0 ? 0 : -26));
        ResReadCapacitor(4,record);
        nodes[j].rn_float.rn_area=j==0 ? ldexp(scale,24) : scale;
        if(previous)previous->rn_more=&nodes[j];else head=&nodes[j];
        previous=&nodes[j];
    }
    ResExtNode *a=ResExtInitNode(HashFind(&ResNodeTable,"ICSTUDIO_A"));
    ResExtNode *b=ResExtInitNode(HashFind(&ResNodeTable,"ICSTUDIO_B"));
    double accumulated_a=mode ? a->cap_couple : a->capacitance;
    double accumulated_b=mode ? b->cap_couple : b->capacitance;
    ResisData data;memset(&data,0,sizeof(data));data.rg_nodecap=accumulated_a;
    ResDistributeCapacitance(head,data.rg_nodecap);
    double minimum=nodes[1].rn_float.rn_area,maximum=minimum;
    for(int i=0;i<count;i++)
    {
        distributed_sum+=nodes[i].rn_float.rn_area;
        if(i>0){if(nodes[i].rn_float.rn_area<minimum)minimum=nodes[i].rn_float.rn_area;if(nodes[i].rn_float.rn_area>maximum)maximum=nodes[i].rn_float.rn_area;}
    }
    snprintf(result,sizeof(result),"{\"order\":%d,\"exponent\":%d,\"mode\":%d,\"nodes\":%d,\"accumulated_a\":%.17g,\"accumulated_b\":%.17g,\"transferred_total\":%.17g,\"large_node\":%.17g,\"small_min\":%.17g,\"small_max\":%.17g,\"distributed_sum\":%.17g}",order,exponent,mode,count,accumulated_a,accumulated_b,(double)data.rg_nodecap,(double)nodes[0].rn_float.rn_area,minimum,maximum,distributed_sum);
    TxPrintf("CAP_RESULT %s\n",result);
}
