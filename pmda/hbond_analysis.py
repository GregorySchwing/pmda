# -*- Mode: python; tab-width: 4; indent-tabs-mode:nil; coding:utf-8 -*-
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
#
# PMDA
# Copyright (c) 2019 The MDAnalysis Development Team and contributors
# (see the file AUTHORS for the full list of names)
#
# Released under the GNU Public Licence, v2 or any higher version

"""Hydrogen Bond Analysis --- :mod:`pmda.hbond_analysis`
========================================================

This module contains parallel versions of analysis tasks in
:mod:`MDAnalysis.analysis.hbonds.hbond_analysis`.


See Also
--------
MDAnalysis.analysis.hbonds.hbond_analysis


Classes
-------

.. autoclass:: HydrogenBondAnalysis
   :members:

"""
from __future__ import absolute_import, division

import numpy as np

from MDAnalysis.lib.distances import capped_distance, calc_angles

import MDAnalysis as mda

from .parallel import ParallelAnalysisBase


class HydrogenBondAnalysis(ParallelAnalysisBase):
    """
    Perform an analysis of hydrogen bonds in a Universe.
    """

    def __init__(self, universe, donors_sel=None, hydrogens_sel=None,
                 acceptors_sel=None, d_h_cutoff=1.2, d_a_cutoff=3.0,
                 d_h_a_angle_cutoff=150, update_selections=True):
        """Set up atom selections and geometric criteria for finding hydrogen
        bonds in a Universe.

        Parameters
        ----------
        universe : Universe
            MDAnalysis Universe object
        donors_sel : str
            Selection string for the hydrogen bond donor atoms. If the
            universe topology contains bonding information, leave
            :attr:`donors_sel` as `None` so that donor-hydrogen pairs can be
            correctly identified.
        hydrogens_sel : str
            Selection string for the hydrogen bond hydrogen atoms. Leave as
            `None` to guess which hydrogens to use in the analysis using
            :attr:`guess_hydrogens`. If :attr:`hydrogens_sel` is left as
            `None`, also leave :attr:`donors_sel` as None so that
            donor-hydrogen pairs can be correctly identified.
        acceptors_sel : str
            Selection string for the hydrogen bond acceptor atoms. Leave as
            `None` to guess which atoms to use in the analysis using
            :attr:`guess_acceptors`
        d_h_cutoff : float (optional)
            Distance cutoff used for finding donor-hydrogen pairs [1.2]. Only
            used to find donor-hydrogen pairs if the universe topology does
            not contain bonding information
        d_a_cutoff : float (optional)
            Distance cutoff for hydrogen bonds. This cutoff refers to the
            D-A distance. [3.0]
        d_h_a_angle_cutoff: float (optional)
            D-H-A angle cutoff for hydrogen bonds, in degrees. [150]
        update_selections: bool (optional)
            Whether or not to update the acceptor, donor and hydrogen lists at
            each frame. [True]

        Examples
        --------

        The simplest use case is to allow :class:`HydrogenBondAnalysis` to
        guess the acceptor and hydrogen atoms, and to identify donor-hydrogen
        pairs via the bonding information in the topology::

          import MDAnalysis
          from pmda.hbond_analysis import HydrogenBondAnalysis as HBA

          u = MDAnalysis.Universe(psf, trajectory)

          hbonds = HBA(universe=u)
          hbonds.run()

        It is also possible to specify which hydrogens and acceptors to use
        in the analysis. For example, to find all hydrogen bonds in water::

          import MDAnalysis
          from pmda.hbond_analysis import HydrogenBondAnalysis as HBA

          u = MDAnalysis.Universe(psf, trajectory)

          hbonds = HBA(universe=u,
                       hydrogens_sel='resname TIP3 and name H1 H2',
                       acceptors_sel='resname TIP3 and name OH2')
          hbonds.run()

        Alternatively, :attr:`hydrogens_sel` and :attr:`acceptors_sel` may be
        generated via the :attr:`guess_hydrogens` and :attr:`guess_acceptors`.
        This selection strings may then be modified prior to calling
        :attr:`run`, or a subset of the universe may be used to guess the
        atoms. For example, find hydrogens and acceptors belonging to a
        protein::

          import MDAnalysis
          from pmda.hbond_analysis import HydrogenBondAnalysis as HBA

          u = MDAnalysis.Universe(psf, trajectory)

          hbonds = HBA(universe=u)
          hbonds.hydrogens_sel = hbonds.guess_hydrogens("protein")
          hbonds.acceptors_sel = hbonds.guess_acceptors("protein")
          hbonds.run()

        Slightly more complex selection strings are also possible.
        For example, to find hydrogen bonds involving a protein and
        any water molecules within 10 Å of the protein (which may be useful
        for subsequently finding the lifetime of protein-water hydrogen bonds
        or finding water-bridging hydrogen bond paths)::

          import MDAnalysis
          from pmda.hbond_analysis import HydrogenBondAnalysis as HBA

          u = MDAnalysis.Universe(psf, trajectory)

          hbonds = HBA(universe=u)

          protein_hydrogens_sel = hbonds.guess_hydrogens("protein")
          protein_acceptors_sel = hbonds.guess_acceptors("protein")

          water_hydrogens_sel = "resname TIP3 and name H1 H2"
          water_acceptors_sel = "resname TIP3 and name OH2"

          hbonds.hydrogens_sel = f"({protein_hydrogens_sel}) or
                    ({water_hydrogens_sel} and around 10 not resname TIP3})"
          hbonds.acceptors_sel = f"({protein_acceptors_sel}) or
                    ({water_acceptors_sel} and around 10 not resname TIP3})"
          hbonds.run()

        It is highly recommended that a topology with bonding information is
        used to generate the universe, e.g `PSF`, `TPR`, or `PRMTOP` files.
        This is the only method by which it can be guaranteed that
        donor-hydrogen pairs are correctly identified. However, if, for
        example, a `PDB` file is used instead, a :attr:`donors_sel` may be
        provided along with a :attr:`hydrogens_sel` and the donor-hydrogen
        pairs will be identified via a distance cutoff, :attr:`d_h_cutoff`::

          import MDAnalysis
          from pmda.hbond_analysis import HydrogenBondAnalysis as HBA

          u = MDAnalysis.Universe(pdb, trajectory)

          hbonds = HBA(
            universe=u,
            donors_sel='resname TIP3 and name OH2',
            hydrogens_sel='resname TIP3 and name H1 H2',
            acceptors_sel='resname TIP3 and name OH2',
            d_h_cutoff=1.2
          )
          hbonds.run()
        """

        ag = universe.atoms
        super(HydrogenBondAnalysis, self).__init__(universe, (ag, ))
        self.donors_sel = donors_sel
        self.hydrogens_sel = hydrogens_sel
        self.acceptors_sel = acceptors_sel
        self.d_h_cutoff = d_h_cutoff
        self.d_a_cutoff = d_a_cutoff
        self.d_h_a_angle = d_h_a_angle_cutoff
        self.update_selections = update_selections
        self._positions = ag.positions

    def guess_hydrogens(self, selection='all', max_mass=1.1, min_charge=0.3):
        """Guesses which hydrogen atoms should be used in the analysis.

        Parameters
        ----------
        selection: str (optional)
            Selection string for atom group from which hydrogens will be
            identified.
        max_mass: float (optional)
            Maximum allowed mass of a hydrogen atom.
        min_charge: float (optional)
            Minimum allowed charge of a hydrogen atom.

        Returns
        -------
        potential_hydrogens: str
            String containing the :attr:`resname` and :attr:`name` of all
            hydrogen atoms potentially capable of forming hydrogen bonds.

        Notes
        -----
        This function makes use of atomic masses and atomic charges to
        identify which atoms are hydrogen atoms that are capable of
        participating in hydrogen bonding. If an atom has a mass less than
        :attr:`max_mass` and an atomic charge greater than :attr:`min_charge`
        then it is considered capable of participating in hydrogen bonds.

        If :attr:`hydrogens_sel` is `None`, this function is called to guess
        the selection.

        Alternatively, this function may be used to quickly generate a
        :class:`str` of potential hydrogen atoms involved in hydrogen bonding.
        This str may then be modified before being used to set the attribute
        :attr:`hydrogens_sel`.
        """

        u = self._universe()
        ag = u.select_atoms(selection)
        hydrogens_ag = ag[
            np.logical_and(
                ag.masses < max_mass,
                ag.charges > min_charge
            )
        ]

        hydrogens_list = np.unique(
            [
                '(resname {} and name {})'.format(r, p)
                for r, p in zip(hydrogens_ag.resnames, hydrogens_ag.names)
            ]
        )

        return " or ".join(hydrogens_list)

    def guess_donors(self, selection='all', max_charge=-0.5):
        """Guesses which atoms could be considered donors in the analysis.
        Only use if the universe topology does not contain bonding
        information, otherwise donor-hydrogen pairs may be incorrectly
        assigned.

        Parameters
        ----------
        selection: str (optional)
            Selection string for atom group from which donors will be
            identified.
        max_charge: float (optional)
            Maximum allowed charge of a donor atom.

        Returns
        -------
        potential_donors: str
            String containing the :attr:`resname` and :attr:`name` of all
            atoms that potentially capable of forming hydrogen bonds.

        Notes
        -----
        This function makes use of and atomic charges to identify which atoms
        could be considered donor atoms in the hydrogen bond analysis. If an
        atom has an atomic charge less than :attr:`max_charge`, and it is
        within :attr:`d_h_cutoff` of a hydrogen atom, then it is considered
        capable of participating in hydrogen bonds.

        If :attr:`donors_sel` is `None`, and the universe topology does not
        have bonding information, this function is called to guess the
        selection.

        Alternatively, this function may be used to quickly generate a
        :class:`str` of potential donor atoms involved in hydrogen bonding.
        This :class:`str` may then be modified before being used to set the
        attribute :attr:`donors_sel`.

        """

        # We need to know `hydrogens_sel` before we can find donors
        # Use a new variable `hydrogens_sel` so that we do not set
        # `self.hydrogens_sel` if it is currently `None`
        if not self.hydrogens_sel:
            hydrogens_sel = self.guess_hydrogens()
        else:
            hydrogens_sel = self.hydrogens_sel
        u = self._universe()
        hydrogens_ag = u.select_atoms(hydrogens_sel)

        ag = hydrogens_ag.residues.atoms.select_atoms(
            "({donors_sel}) and around {d_h_cutoff} {hydrogens_sel}".format(
                donors_sel=selection,
                d_h_cutoff=self.d_h_cutoff,
                hydrogens_sel=hydrogens_sel
            )
        )
        donors_ag = ag[ag.charges < max_charge]
        donors_list = np.unique(
            [
                '(resname {} and name {})'.format(r, p)
                for r, p in zip(donors_ag.resnames, donors_ag.names)
            ]
        )

        return " or ".join(donors_list)

    def guess_acceptors(self, selection='all', max_charge=-0.5):
        """Guesses which atoms could be considered acceptors in the analysis.

        Parameters
        ----------
        selection: str (optional)
            Selection string for atom group from which acceptors will be
            identified.
        max_charge: float (optional)
            Maximum allowed charge of an acceptor atom.

        Returns
        -------
        potential_acceptors: str
            String containing the :attr:`resname` and :attr:`name` of all
            atoms that potentially capable of forming hydrogen bonds.

        Notes
        -----
        This function makes use of and atomic charges to identify which atoms
        could be considered acceptor atoms in the hydrogen bond analysis.
        If an atom has an atomic charge less than :attr:`max_charge` then it
        is considered capable of participating in hydrogen bonds.

        If :attr:`acceptors_sel` is `None`, this function is called to guess
        the selection.

        Alternatively, this function may be used to quickly generate a
        :class:`str` of potential acceptor atoms involved in hydrogen bonding.
        This :class:`str` may then be modified before being used to set the
        attribute :attr:`acceptors_sel`.
        """

        u = self._universe()
        ag = u.select_atoms(selection)
        acceptors_ag = ag[ag.charges < max_charge]
        acceptors_list = np.unique(
            [
                '(resname {} and name {})'.format(r, p)
                for r, p in zip(acceptors_ag.resnames, acceptors_ag.names)
            ]
        )

        return " or ".join(acceptors_list)

    def _get_dh_pairs(self, u):
        """Finds donor-hydrogen pairs.

        Returns
        -------
        donors, hydrogens: AtomGroup, AtomGroup
            AtomGroups corresponding to all donors and all hydrogens.
            AtomGroups are ordered such that, if zipped, will produce a list
            of donor-hydrogen pairs.
        """

        # If donors_sel is not provided, use topology to find d-h pairs
        if not self.donors_sel:

            if not (hasattr(u, 'bonds') and len(u.bonds) != 0):
                raise ValueError(
                    'Cannot assign donor-hydrogen pairs via topology as no'
                    'bonded information is present. ',
                    'Please either: ',
                    'load a topology file with bonded information; ',
                    'use the guess_bonds() topology guesser; ',
                    'or set HydrogenBondAnalysis.donors_sel so that a '
                    'distance cutoff can be used.')

            hydrogens = u.select_atoms(self.hydrogens_sel)
            donors = sum(h.bonded_atoms[0] for h in hydrogens)

        # Otherwise, use d_h_cutoff as a cutoff distance
        else:

            hydrogens = u.select_atoms(self.hydrogens_sel)
            donors = u.select_atoms(self.donors_sel)
            donors_indices, hydrogen_indices = capped_distance(
                donors.positions,
                hydrogens.positions,
                max_cutoff=self.d_h_cutoff,
                box=u.dimensions,
                return_distances=False
            ).T

            donors = donors[donors_indices]
            hydrogens = hydrogens[hydrogen_indices]

        return donors, hydrogens

    def _prepare(self):
        u = mda.Universe(self._top, self._traj)
        self.hbonds = []
        self.frames = np.arange(self.start, self.stop, self.step)
        self.timesteps = (self.frames*u.trajectory.dt) + u.trajectory[0].time
        # Set atom selections if they have not been provided
        if not self.acceptors_sel:
            self.acceptors_sel = self.guess_acceptors()
        if not self.hydrogens_sel:
            self.hydrogens_sel = self.guess_hydrogens()

        # Select atom groups
        acceptors = u.select_atoms(self.acceptors_sel)
        donors, hydrogens = self._get_dh_pairs(u)
        self._acceptors_ids = acceptors.ids
        self._donors_ids = donors.ids
        self._hydrogens_ids = hydrogens.ids

    def _single_frame(self, ts, atomgroups):
        u = atomgroups[0].universe

        box = ts.dimensions

        # Update donor-hydrogen pairs if necessary
        if self.update_selections:
            acceptors = u.select_atoms(self.acceptors_sel)
            donors, hydrogens = self._get_dh_pairs(u)
        else:
            acceptors = u.atoms[self._acceptors_ids]
            donors = u.atoms[self._donors_ids]
            hydrogens = u.atoms[self._hydrogens_ids]
        # find D and A within cutoff distance of one another
        # min_cutoff = 1.0 as an atom cannot form a hydrogen bond with itself
        d_a_indices, d_a_distances = capped_distance(
            donors.positions,
            acceptors.positions,
            max_cutoff=self.d_a_cutoff,
            min_cutoff=1.0,
            box=box,
            return_distances=True,
        )

        # Remove D-A pairs more than d_a_cutoff away from one another
        tmp_donors = donors[d_a_indices.T[0]]
        tmp_hydrogens = hydrogens[d_a_indices.T[0]]
        tmp_acceptors = acceptors[d_a_indices.T[1]]

        # Find D-H-A angles greater than d_h_a_angle_cutoff
        d_h_a_angles = np.rad2deg(
            calc_angles(
                tmp_donors.positions,
                tmp_hydrogens.positions,
                tmp_acceptors.positions,
                box=box
            )
        )
        hbond_indices = np.where(d_h_a_angles > self.d_h_a_angle)[0]

        # Retrieve atoms, distances and angles of hydrogen bonds
        hbond_donors = tmp_donors[hbond_indices]
        hbond_hydrogens = tmp_hydrogens[hbond_indices]
        hbond_acceptors = tmp_acceptors[hbond_indices]
        hbond_distances = d_a_distances[hbond_indices]
        hbond_angles = d_h_a_angles[hbond_indices]

        # Store data on hydrogen bonds found at this frame
        hbonds = [[], [], [], [], [], []]
        hbonds[0].extend(np.full_like(hbond_donors, ts.frame))
        hbonds[1].extend(hbond_donors.ids)
        hbonds[2].extend(hbond_hydrogens.ids)
        hbonds[3].extend(hbond_acceptors.ids)
        hbonds[4].extend(hbond_distances)
        hbonds[5].extend(hbond_angles)
        return np.asarray(hbonds).T

    def _conclude(self):
        self.hbonds = np.vstack(self._results)

    def count_by_time(self):
        """Counts the number of hydrogen bonds per timestep.

        Returns
        -------
        counts : numpy.ndarray
             Contains the total number of hydrogen bonds found at each
             timestep.
             Can be used along with :attr:`HydrogenBondAnalysis.timesteps` to
             plot the number of hydrogen bonds over time.
        """

        indices, tmp_counts = np.unique(self.hbonds[:, 0], axis=0,
                                        return_counts=True)

        indices -= self.start
        indices /= self.step

        counts = np.zeros_like(self.frames)
        counts[indices.astype("int")] = tmp_counts
        return counts

    def count_by_type(self):
        """Counts the total number of each unique type of hydrogen bond.

        Returns
        -------
        counts : numpy.ndarray
             Each row of the array contains the donor resname, donor atom
             type, acceptor resname, acceptor atom type and the total number
             of times the hydrogen bond was found.

        Note
        ----
        Unique hydrogen bonds are determined through a consideration of the
        resname and atom type of the donor and acceptor atoms in a hydrogen
        bond.
        """
        u = self._universe()
        d = u.atoms[self.hbonds[:, 1].astype("int")]
        a = u.atoms[self.hbonds[:, 3].astype("int")]

        tmp_hbonds = np.array([d.resnames, d.types, a.resnames, a.types],
                              dtype=np.str).T
        hbond_type, type_counts = np.unique(tmp_hbonds, axis=0,
                                            return_counts=True)
        hbond_type_list = []
        for hb_type, hb_count in zip(hbond_type, type_counts):
            hbond_type_list.append(
                [":".join(hb_type[:2]), ":".join(hb_type[2:4]), hb_count])

        return np.array(hbond_type_list)

    def count_by_ids(self):
        """Counts the total number hydrogen bonds formed by unique
        combinations of donor, hydrogen and acceptor atoms.

        Returns
        -------
        counts : numpy.ndarray
             Each row of the array contains the donor atom id, hydrogen atom
             id, acceptor atom id and the total number of times the hydrogen
             bond was observed. The array is sorted by frequency of
             occurrence.

        Note
        ----
        Unique hydrogen bonds are determined through a consideration of the
        hydrogen atom id and acceptor atom id in a hydrogen bond.
        """

        u = self._universe()
        d = u.atoms[self.hbonds[:, 1].astype("int")]
        h = u.atoms[self.hbonds[:, 2].astype("int")]
        a = u.atoms[self.hbonds[:, 3].astype("int")]

        tmp_hbonds = np.array([d.ids, h.ids, a.ids]).T
        hbond_ids, ids_counts = np.unique(tmp_hbonds, axis=0,
                                          return_counts=True)

        # Find unique hbonds and sort rows so that most frequent observed
        # bonds are at the top of the array
        unique_hbonds = np.concatenate((hbond_ids, ids_counts[:, None]),
                                       axis=1)
        unique_hbonds = unique_hbonds[unique_hbonds[:, 3].argsort()[::-1]]

        return unique_hbonds

    def _universe(self):
        # A Universe containing position information is needed for guessing
        # donors and acceptors.
        u = mda.Universe(self._top)
        if not hasattr(u.atoms, 'positions'):
            u.load_new(self._positions)
        return u

    @staticmethod
    def _reduce(res, result_single_frame):
        """ Use numpy array append to combine results"""
        if isinstance(res, list) and len(res) == 0:
            # Convert res from an empty list to a numpy array
            # which has the same shape as the single frame result
            res = result_single_frame
        else:
            # Add two numpy arrays
            res = np.append(res, result_single_frame, axis=0)
        return res
