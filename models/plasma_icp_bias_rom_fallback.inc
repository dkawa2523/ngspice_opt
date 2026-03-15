* plasma_icp_bias_rom_fallback.inc
* Smooth, research-oriented ICP+Bias two-port surrogate for ngspice.
* Coil port and bias port share one slow internal plasma-state proxy.
* This is NOT a first-principles plasma model.

.subckt PLASMA_ICP_BIAS CP CN BP BN params: GCOIL0=1e-3 KGCOIL=5e-4 LCOIL0=2u G0=2e-3 KG=0.2 CBP0=20p CBG0=20p CBNL=8p VBSCALE=80 KCOIL=2e-3 KBIAS=5e-2 TAU=8e-7

* Shared slow state proxy
CSTATE D 0 1
RSTATE D 0 {TAU}

* Current sensors internal to the subckt
VMC CP CPH 0
VMB BP BPH 0

* State excitation from coil current and bias voltage
BSTATE D 0 I = { KCOIL*abs(I(VMC)) + KBIAS*abs(V(BPH,BN))/VBSCALE }

* Coil branch: inductive port + density-dependent dissipative loading
LCOIL CPH CN {LCOIL0}
BCOILLOSS CPH CN I = { (GCOIL0 + KGCOIL*abs(V(D)))*V(CPH,CN) }
RCOILLEAK CP CN 1e12

* Bias branch: sheath + bulk conduction, sharing the same state D
RBULKLEAK B BN 1e12
BBULK B BN I = { (G0*(1 + KG*abs(V(D))))*tanh(V(B,BN)/VBSCALE) }
CBP BPH B Q = { (CBP0*(1 + 0.1*abs(V(D))))*V(BPH,B) + CBNL*VBSCALE*atan(V(BPH,B)/VBSCALE) }
CBG B BN Q = { (CBG0*(1 + 0.1*abs(V(D))))*V(B,BN) + CBNL*VBSCALE*atan(V(B,BN)/VBSCALE) }
RBIASLEAK BP BN 1e12

.ends
