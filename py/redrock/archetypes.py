"""
Classes and functions for archetypes.
"""

import os
from glob import glob
from astropy.io import fits
import numpy as np
from scipy.interpolate import interp1d
import scipy.special

from .zscan import calc_zchi2_one

from .rebin import trapz_rebin


class Archetype():
    """Class to store all different archetypes from the same spectype.

    The archetype data are read from a redrock-format archetype file.

    Args:
        filename (str): the path to the archetype file

    """
    def __init__(self, filename):

        # Load the file
        h = fits.open(filename, memmap=False)

        hdr = h['ARCHETYPES'].header
        self.flux = np.asarray(h['ARCHETYPES'].data['ARCHETYPE'])
        self._narch = self.flux.shape[0]
        self._nwave = self.flux.shape[1]
        self._rrtype = hdr['RRTYPE'].strip()
        self._subtype = np.array(np.char.strip(h['ARCHETYPES'].data['SUBTYPE'].astype(str)))
        self._subtype = np.char.add(np.char.add(self._subtype,'_'),np.arange(self._narch,dtype=int).astype(str))
        self._full_type = np.char.add(self._rrtype+':::',self._subtype)
        self._version = hdr['VERSION']

        self.wave = np.asarray(hdr['CRVAL1'] + hdr['CDELT1']*np.arange(self.flux.shape[1]))
        if hdr['LOGLAM']:
            self.wave = 10**self.wave

        self._archetype = {}
        self._archetype['INTERP'] = np.array([None]*self._narch)
        for i in range(self._narch):
            self._archetype['INTERP'][i] = interp1d(self.wave,self.flux[i,:],fill_value='extrapolate',kind='linear')

        h.close()

        return
    def rebin_template(self,index,z,dwave,trapz=True):
        """
        """
        if trapz:
            return {hs:trapz_rebin((1.+z)*self.wave, self.flux[index], wave) for hs, wave in dwave.items()}
        else:
            return {hs:self._archetype['INTERP'][index](wave/(1.+z)) for hs, wave in dwave.items()}

    def eval(self, subtype, dwave, coeff, wave, z):
        """

        """

        deg_legendre = (coeff!=0.).size-1
        index = np.arange(self._narch)[self._subtype==subtype][0]

        w = np.concatenate([ w for w in dwave.values() ])
        wave_min = w.min()
        wave_max = w.max()
        legendre = np.array([scipy.special.legendre(i)( (wave-wave_min)/(wave_max-wave_min)*2.-1. ) for i in range(deg_legendre)])
        binned = trapz_rebin((1+z)*self.wave, self.flux[index], wave)
        flux = np.append(binned[None,:],legendre, axis=0)
        flux = flux.T.dot(coeff).T / (1+z)

        return flux

    def get_best_archetype(self,spectra,weights,flux,wflux,dwave,z,legendre):
        """Get the best archetype for the given redshift and spectype.

        Args:
            spectra (list): list of Spectrum objects.
            weights (array): concatenated spectral weights (ivar).
            flux (array): concatenated flux values.
            wflux (array): concatenated weighted flux values.
            dwave (dic): dictionary of wavelength grids
            z (float): best redshift
            legendre (dic): legendre polynomial

        Returns:
            chi2 (float): chi2 of best archetype
            zcoef (array): zcoef of best archetype
            fulltype (str): fulltype of best archetype

        """

        nleg = legendre[list(legendre.keys())[0]].shape[0]
        zzchi2 = np.zeros(self._narch, dtype=np.float64)
        zzcoeff = np.zeros((self._narch, nleg+1), dtype=np.float64)

        # TODO: should we look at the value of zzcoeff[0] and if negative
        #   set the chi2 to very big?
        for i in range(self._narch):
            binned = self.rebin_template(i, z, dwave,trapz=False)
            tdata = { hs:np.append(binned[hs][:,None],legendre[hs].transpose(), axis=1 ) for hs, wave in dwave.items() }
            zzchi2[i], zzcoeff[i] = calc_zchi2_one(spectra, weights, flux, wflux, tdata)

        iBest = np.argmin(zzchi2)
        binned = self.rebin_template(iBest, z, dwave,trapz=True)
        tdata = { hs:np.append(binned[hs][:,None],legendre[hs].transpose(), axis=1 ) for hs, wave in dwave.items() }
        zzchi2, zzcoeff = calc_zchi2_one(spectra, weights, flux, wflux, tdata)

        return zzchi2, zzcoeff, self._full_type[iBest]


class All_archetypes():
    """Class to store all different archetypes of all the different spectype.

    Args:
        lstfilename (lst str): List of file to get the templates from
        archetypes_dir (str): Directory to the archetypes

    """
    def __init__(self, lstfilename=None, archetypes_dir=None):

        # Get list of path to archetype
        if lstfilename is None:
            lstfilename = find_archetypes(archetypes_dir)

        # Load archetype
        self.archetypes = {}
        for f in lstfilename:
            archetype = Archetype(f)
            print('DEBUG: Found {} archetypes for SPECTYPE {} in file {}'.format(archetype._narch, archetype._rrtype, f) )
            self.archetypes[archetype._rrtype] = archetype

        return

def find_archetypes(archetypes_dir=None):
    """Return list of rrarchetype-\*.fits archetype files

    Search directories in this order, returning results from first one found:
        - archetypes_dir
        - $RR_ARCHETYPE_DIR
        - <redrock_code>/archetypes/

    Args:
        archetypes_dir (str): optional directory containing the archetypes.

    Returns:
        list: a list of archetype files.

    """
    if archetypes_dir is None:
        if 'RR_ARCHETYPE_DIR' in os.environ:
            archetypes_dir = os.environ['RR_ARCHETYPE_DIR']
        else:
            thisdir = os.path.dirname(__file__)
            archdir = os.path.join(os.path.abspath(thisdir), 'archetypes')
            if os.path.exists(archdir):
                archetypes_dir = archdir
            else:
                raise IOError("ERROR: can't find archetypes_dir, $RR_ARCHETYPE_DIR, or {rrcode}/archetypes/")

    return sorted(glob(os.path.join(archetypes_dir, 'rrarchetype-*.fits')))
