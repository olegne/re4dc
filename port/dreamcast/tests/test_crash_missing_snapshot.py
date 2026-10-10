"""The fatal handler preserves the first PVR state before logging or sleeping."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]

def function(source, signature):
    start=source.index(signature);pos=source.index('{',start)+1;depth=1
    while depth:
        depth+=(source[pos]=='{')-(source[pos]=='}');pos+=1
    return source[start:pos]

class MissingSnapshot(unittest.TestCase):
    def test_first_failure_and_uninitialized_pvr(self):
        base=ROOT/'port/dreamcast/game/platform'
        crash=(base/'crash_screen.cpp').read_text();mem=(base/'mem.cpp').read_text()
        a=crash.index('struct MissingSnapshot {');b=crash.index('void capture_missing(',a)
        code=r'''
#include <cassert>
#include <cstdio>
#include <cstring>
using uint32_t=unsigned;
struct pvr_stats_t {unsigned frame_count,vbl_count;};
bool initialized=true;unsigned frames=12,vbl=100,reads=0,restores=0,logs=0;
uint32_t asic[3]={0x12345678,0x9abcdef0,0x00000005};
#define ASIC_ACK_A (&asic[0])
#define ASIC_ACK_B (&asic[1])
#define ASIC_ACK_C (&asic[2])
int irq_disable(){return 37;}
void irq_restore(int old){assert(old==37);++restores;}
unsigned re4dc_ui_frame(){return 44;}
int pvr_get_stats(pvr_stats_t* p){p->frame_count=frames;p->vbl_count=vbl;return initialized?0:-1;}
int pvr_check_ready(){assert(initialized);return -1;}
extern "C" int pvr_present_pending() __attribute__((weak));
#if WITH_ASYNC
extern "C" int pvr_present_pending(){return 1;}
#endif
enum {PVR_TA_VERTBUF_START=1,PVR_TA_VERTBUF_POS,PVR_TA_VERTBUF_END,PVR_TA_OPB_START,PVR_TA_OPB_POS,PVR_TA_OPB_END,PVR_ISP_VERTBUF_ADDR,PVR_TA_OPB_INIT};
unsigned read_pvr(unsigned reg){assert(initialized);++reads;return reg*0x100;}
#define PVR_GET(reg) read_pvr(reg)
''' + crash[a:b]+function(crash,'void capture_missing(')+r'''
void re4dc_crash_screen_missing(const char* name){capture_missing(name);}
void re4dc_log(const char*,const char*){assert(g_missing.valid);++logs;}
void thd_sleep(int ms){assert(ms==1000);throw 17;}
''' + function(mem,'void re4dc_missing(')+r'''
int main(){
    try {re4dc_missing("native stream completion fence failed");assert(false);} catch(int n){assert(n==17);}
    assert(logs==1 && g_missing.valid && g_missing.pvr_valid && g_missing.ui==44);
    assert(g_missing.frames==12 && g_missing.vbl==100 && g_missing.ta_ready==-1);
    assert(g_missing.pending==(WITH_ASYNC?1:-1));
    assert(reads==8 && g_missing.vtx[1]==0x200 && g_missing.opb[1]==0x500 && g_missing.isp==0x700);
    assert(g_missing.opb_init==0x800 && g_missing.asic[0]==0x12345678 &&
           g_missing.asic[1]==0x9abcdef0 && g_missing.asic[2]==5);
    asic[0]=asic[1]=asic[2]=0;
    frames=99;vbl=800;capture_missing("later failure");
    assert(g_missing.frames==12 && g_missing.vbl==100 && reads==8 && restores==2);
    assert(g_missing.opb_init==0x800 && g_missing.asic[0]==0x12345678 && g_missing.asic[2]==5);
    assert(std::strcmp(g_missing.reason,"native stream completion fence failed")==0);
    g_missing={};initialized=false;capture_missing(nullptr);
    assert(g_missing.valid && !g_missing.pvr_valid && reads==8 && std::strcmp(g_missing.reason,"unknown")==0);
    g_missing={};char long_name[256];std::memset(long_name,'x',255);long_name[255]=0;capture_missing(long_name);
    assert(std::strlen(g_missing.reason)==79 && g_missing.reason[79]==0 && reads==8);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'check.cpp').write_text(code)
            for enabled in (0,1):
                subprocess.run(['g++','-std=c++17','-fsanitize=address,undefined','-DRE4DC_SERIAL_LOG=0','-I',str(base/'include'),f'-DWITH_ASYNC={enabled}',str(p/'check.cpp'),'-o',str(p/'check')],check=True)
                subprocess.run([str(p/'check')],check=True)

if __name__=='__main__':unittest.main()
