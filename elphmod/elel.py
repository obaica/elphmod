#/usr/bin/env python

from . import bravais, dispersion

import numpy as np

def read_orbital_Coulomb_interaction(comm, filename, nq, no):
    """Read Coulomb interaction in orbital basis.."""

    U = np.empty((nq, nq, no, no, no, no), dtype=complex)

    if comm.rank == 0:
        with open(filename) as data:
            next(data)
            next(data)

            for line in data:
                columns = line.split()

                q1, q2 = [int(round(float(q) * nq)) % nq for q in columns[0:2]]

                i, j, k, l = [int(n) - 1 for n in columns[3:7]]

                U[q1, q2, j, i, l, k] \
                    = float(columns[7]) + 1j * float(columns[8])

    comm.Bcast(U)

    return U

def read_band_Coulomb_interaction(comm, filename, nQ, nk):
    """Read Coulomb interaction for single band in band basis.."""

    U = np.empty((nQ, nk, nk, nk, nk), dtype=complex)

    if comm.rank == 0:
        with open(filename) as data:
            for iQ in range(len(Q)):
                for k1 in range(nk):
                    for k2 in range(nk):
                        for K1 in range(nk):
                            for K2 in range(nk):
                                ReU, ImU = list(map(float, next(data).split()))
                                U[iQ, k1, k2, K1, K2] = ReU + 1j * ImU

    comm.Bcast(U)

    return U

def orbital2band(comm, U, H, nk, band=0):
    """Transform Coulomb interaction from orbital basis onto single band."""

    nq, nq, no, no, no, no = U.shape

    # get eigenvectors of Hamiltonian:

    k = np.empty((nk * nk, 2))

    n = 0
    for k1 in range(nk):
        for k2 in range(nk):
            k[n] = k1, k2
            n += 1

    k *= 2 * np.pi / nk

    eps, psi = dispersion(comm, H, k,
        vectors=True, gauge=True) # psi[k, a, n] = <a k|n k>

    psi = np.reshape(psi[:, :, band], (nk, nk, no))

    # distribute work among processors:

    Q = elphmod.bravais.irreducibles(nq)

    size = len(Q) * nk ** 4

    points = np.empty((size, 5))

    n = 0
    for iq, (q1, q2) in enumerate(Q):
        q1 *= nk // nq
        q2 *= nk // nq

        for k1 in range(nk):
            for k2 in range(nk):
                for K1 in range(nk):
                    for K2 in range(nk):
                        points[n] = q1, q2, k1, k2, K1, K2
                        n += 1

    sizes = np.empty(comm.size, dtype=int)

    if comm.rank == 0:
        sizes[:] = size // comm.size
        sizes[:size % comm.size] += 1

    comm.Bcast(sizes)

    my_points = np.empty((sizes[comm.rank], 5), dtype=int)
    comm.Scatterv((np.arange(points), sizes * 5), my_points)

    # transform from orbital to band basis:

    my_V = np.zeros(sizes[comm.rank], dtype=complex)

    for n, (q1, q2, k1, k2, K1, K2) in enumerate(my_points):
        for a in range(no):
            for b in range(no):
                for c in range(no):
                    for d in range(no):
                        my_V[n] += (U[q1, q2, a, b, c, d]
                            * psi[ K1,             K2,            d].conj() \
                            * psi[ k1,             k2,            b].conj() \
                            * psi[(k1 + q1) % nk, (k2 + q2) % nk, a] \
                            * psi[(K1 - q1) % nk, (K2 - q2) % nk, c]

    V = np.empty((len(Q), nk, nk, nk, nk), dtype=complex)

    comm.Allgatherv(my_V, (V, sizes * 5))

    return V