* plasma_ccp_rom_fallback.inc
* Smooth, research-oriented CCP surrogate for ngspice.
* This is NOT a first-principles plasma model.
* It is designed to be differentiable enough for transient optimization loops.

.subckt PLASMA_CCP P N params: G0=2e-3 KD=0.2 CSP0=20p CSG0=20p CSPNL=10p CSGNL=10p VSCALE=80 ALPHA=5e-2 TAU=5e-7

* D is a slow state that plays the role of a normalized plasma-density / ionization proxy.
CSTATE D 0 1
RSTATE D 0 {TAU}
BSTATE D 0 I = { ALPHA*abs(V(P,N))/VSCALE }

* Internal bulk node
RBULKLEAK B N 1e12

* Smooth bulk conduction
BBULK B N I = { (G0*(1 + KD*abs(V(D))))*tanh(V(B,N)/VSCALE) }

* Powered sheath and grounded sheath as charge-based capacitive elements
CSHP P B Q = { (CSP0*(1 + 0.1*abs(V(D))))*V(P,B) + CSPNL*VSCALE*atan(V(P,B)/VSCALE) }
CSHG B N Q = { (CSG0*(1 + 0.1*abs(V(D))))*V(B,N) + CSGNL*VSCALE*atan(V(B,N)/VSCALE) }

* Numerical bleed
RLEAK P N 1e12

.ends
