"""Defines the SMEFT class that provides the main API to smeft."""

from . import rge
from . import definitions
from . import beta
from . import smpar
from math import sqrt
import numpy as np
import ckmutil.phases, ckmutil.diag
import wilson
from wilson.util import smeftutil


class SMEFT(object):
    """Parameter point in the Standard Model Effective Field Theory."""

    def __init__(self, wc):
        """Initialize the SMEFT instance."""
        self.wc = wc
        self.scale_in = None
        self.scale_high = None
        self.C_in = None
        self._set_initial_wcxf(self, wc)

    def _set_initial_wcxf(self, wc, scale_high=None, get_smpar=True):
        """Load the initial values for Wilson coefficients from a
        wcxf.WC instance.

        Parameters:

        - `scale_high`: since Wilson coefficients are dimensionless in
          smeft but not in WCxf, the high scale in GeV has to be provided.
          If this parameter is None (default), either a previously defined
          value will be used, or the scale attribute of the WC instance will
          be used.
        - `get_smpar`: boolean, optional, defaults to True. If True, an attempt
          is made to determine the SM parameters from the requirement of
          reproducing the correct SM masses and mixings at the electroweak
          scale. As approximations are involved, the result might or might not
          be reliable, depending on the size of the Wilson coefficients
          affecting the SM masses and mixings. If False, Standard Model
          parameters have to be provided separately and are assumed to be in
          the weak basis used for the Warsaw basis as defined in WCxf,
          i.e. in the basis where the down-type and charged lepton mass
          matrices are diagonal.
        """
        import wcxf
        if wc.eft != 'SMEFT':
            raise ValueError("Wilson coefficients use wrong EFT.")
        if wc.basis != 'Warsaw':
            raise ValueError("Wilson coefficients use wrong basis.")
        if scale_high is not None:
            self.scale_high = scale_high
        elif self.scale_high is None:
            self.scale_high = wc.scale
        C = wilson.translate.smeft.wcxf2arrays(wc.dict)
        keys_dim5 = ['llphiphi']
        keys_dim6 = list(set(smeftutil.WC_keys_0f + smeftutil.WC_keys_2f + smeftutil.WC_keys_4f) - set(keys_dim5))
        self.scale_in = wc.scale
        for k in keys_dim5:
            if k in C:
                C[k] = C[k]*self.scale_high
        for k in keys_dim6:
            if k in C:
                C[k] = C[k]*self.scale_high**2
        C = smeftutil.symmetrize(C)
        # fill in zeros for missing WCs
        for k, s in smeftutil.C_keys_shape.items():
            if k not in C and k not in smeftutil.SM_keys:
                if s == 1:
                    C[k] = 0
                else:
                    C[k] = np.zeros(s)
        if self.C_in is None:
            self.C_in = C
        else:
            self.C_in.update(C)
        if get_smpar:
            self.C_in.update(self._get_sm_scale_in())


    def _to_wcxf(self, C_out, scale_out):
        """Return the Wilson coefficients `C_out` as a wcxf.WC instance.

        Note that the Wilson coefficients are rotated into the Warsaw basis
        as defined in WCxf, i.e. to the basis where the down-type and charged
        lepton mass matrices are diagonal."""
        import wcxf
        C = self.rotate_defaultbasis(C_out)
        d = wilson.translate.smeft.arrays2wcxf(C)
        basis = wcxf.Basis['SMEFT', 'Warsaw']
        d = {k: v for k, v in d.items() if k in basis.all_wcs and v != 0}
        keys_dim5 = ['llphiphi']
        keys_dim6 = list(set(smeftutil.WC_keys_0f + smeftutil.WC_keys_2f
                             + smeftutil.WC_keys_4f) - set(keys_dim5))
        for k in d:
            if k.split('_')[0] in keys_dim5:
                d[k] = d[k] / self.scale_high
        for k in d:
            if k.split('_')[0] in keys_dim6:
                d[k] = d[k] / self.scale_high**2
        # d = {k: v for k, v in d.items() if v != 0}
        d = wcxf.WC.dict2values(d)
        wc = wcxf.WC('SMEFT', 'Warsaw', scale_out, d)
        return wc

    def rgevolve(self, scale_out, **kwargs):
        """Solve the SMEFT RGEs from the initial scale to `scale_out`.
        Returns a dictionary with parameters and Wilson coefficients at
        `scale_out`. Additional keyword arguments will be passed to
        the ODE solver `scipy.integrate.odeint`."""
        self._check_initial()
        return rge.smeft_evolve(C_in=self.C_in,
                            scale_high=self.scale_high,
                            scale_in=self.scale_in,
                            scale_out=scale_out,
                            **kwargs)

    def rgevolve_leadinglog(self, scale_out):
        """Compute the leading logarithmix approximation to the solution
        of the SMEFT RGEs from the initial scale to `scale_out`.
        Returns a dictionary with parameters and Wilson coefficients.
        Much faster but less precise that `rgevolve`.
        """
        self._check_initial()
        return rge.smeft_evolve_leadinglog(C_in=self.C_in,
                            scale_high=self.scale_high,
                            scale_in=self.scale_in,
                            scale_out=scale_out)

    def _check_initial(self):
        """Check if initial values and scale as well as the new physics scale
        have been set."""
        if self.C_in is None:
            raise Exception("You have to specify the initial conditions first.")
        if self.scale_in is None:
            raise Exception("You have to specify the initial scale first.")
        if self.scale_high is None:
            raise Exception("You have to specify the high scale first.")

    def rotate_defaultbasis(self, C):
        """Rotate all parameters to the basis where the running down-type quark
        and charged lepton mass matrices are diagonal and where the running
        up-type quark mass matrix has the form V.S, with V unitary and S real
        diagonal, and where the CKM and PMNS matrices have the standard
        phase convention."""
        v = sqrt(2*C['m2'].real/C['Lambda'].real)
        Mep = v/sqrt(2) * (C['Ge'] - C['ephi'] * v**2/self.scale_high**2/2)
        Mup = v/sqrt(2) * (C['Gu'] - C['uphi'] * v**2/self.scale_high**2/2)
        Mdp = v/sqrt(2) * (C['Gd'] - C['dphi'] * v**2/self.scale_high**2/2)
        Mnup = -v**2 * C['llphiphi']
        UeL, Me, UeR = ckmutil.diag.msvd(Mep)
        UuL, Mu, UuR = ckmutil.diag.msvd(Mup)
        UdL, Md, UdR = ckmutil.diag.msvd(Mdp)
        Unu, Mnu = ckmutil.diag.mtakfac(Mnup)
        UuL, UdL, UuR, UdR = ckmutil.phases.rephase_standard(UuL, UdL, UuR, UdR)
        Unu, UeL, UeR = ckmutil.phases.rephase_pmns_standard(Unu, UeL, UeR)
        return definitions.flavor_rotation(C, Uq=UdL, Uu=UuR, Ud=UdR, Ul=UeL, Ue=UeR)

    def _run_sm_scale_in(self, C_out, scale_sm=91.1876):
        """Get the SM parameters at the EW scale, using an estimate `C_out`
        of the Wilson coefficients at that scale, and run them to the
        input scale."""
        # initialize an empty SMEFT instance
        smeft_sm = SMEFT()
        C_in_sm = beta.C_array2dict(np.zeros(9999))
        # set the SM parameters to the values obtained from smpar.smeftpar
        C_SM = smpar.smeftpar(scale_sm, self.scale_high, C_out, basis='Warsaw')
        C_SM = {k: v for k, v in C_SM.items() if k in smeftutil.SM_keys}
        # set the Wilson coefficients at the EW scale to C_out
        C_in_sm.update(C_out)
        C_in_sm.update(C_SM)
        smeft_sm.set_initial(C_in_sm, scale_sm, scale_high=self.scale_high)
        # run up (with 1% relative precision, ignore running of Wilson coefficients)
        C_SM_high = smeft_sm.rgevolve(self.scale_in, newphys=False, rtol=0.01, atol=1)
        C_SM_high = self.rotate_defaultbasis(C_SM_high)
        return {k: v for k, v in C_SM_high.items() if k in smeftutil.SM_keys}

    def _get_sm_scale_in(self, scale_sm=91.1876):
        """Get an estimate of the SM parameters at the input scale by running
        them from the EW scale using constant values for the Wilson coefficients
        (corresponding to their leading log approximated values at the EW
        scale).

        Note that this is not guaranteed to work and will fail if some of the
        Wilson coefficients (the ones affecting the extraction of SM parameters)
        are large."""
        # intialize a copy of ourselves
        _smeft = SMEFT()
        _smeft.set_initial(self.C_in, self.scale_in, self.scale_high)
        # Step 1: run the SM up, using the WCs at scale_input as (constant) estimate
        _smeft.C_in.update(self._run_sm_scale_in(self.C_in, scale_sm=scale_sm))
        # Step 2: run the WCs down in LL approximation
        C_out = _smeft.rgevolve_leadinglog(scale_sm)
        # Step 3: run the SM up again, this time using the WCs at scale_sm as (constant) estimate
        return self._run_sm_scale_in(C_out, scale_sm=scale_sm)
