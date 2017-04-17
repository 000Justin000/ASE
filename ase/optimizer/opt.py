#--------------------------------------------------
import sys, os, math, numpy
import openbabel, pybel, ase
#--------------------------------------------------
from mpi4py import MPI
#--------------------------------------------------
from ase import Atoms
from ase.visualize import view
from ase.optimize import BFGS
from ase.optimize import QuasiNewton
from ase.calculators.lj import LennardJones
from ase.calculators.emt import EMT
from ase.calculators.lammpsrun import LAMMPS
from ase.calculators.qchem import QChem
from ase.constraints import FixInternals, Hookean
#--------------------------------------------------

#--------------------------------------------------
def pyb2ase(pybmol, pid):
    pybmol.write("pdb", "tmp"+"{:04d}".format(pid)+".pdb", overwrite=True)
    asemol = ase.io.read("tmp"+"{:04d}".format(pid)+".pdb")
    os.remove("tmp"+"{:04d}".format(pid)+".pdb")
    #--------------
    return asemol

# #--------------------------------------------------
# def geomOptMM(pybmol, tcs, MMFF, tol):
#     #----------------------------------------
#     constraints = openbabel.OBFFConstraints()
#     #----------------------------------------
#     if tcs is not None:
#         for tc in tcs:
#             constraints.AddTorsionConstraint(tc[0][0],tc[0][1],tc[0][2],tc[0][3], tc[1]*(360/(2*math.pi)))
#     #----------------------------------------
#     FF = pybel._forcefields[MMFF]
#     FF.Setup(pybmol.OBMol, constraints)
#     FF.SetConstraints(constraints)
#     #----------------------------------------
#     EE = FF.Energy()
#     dE = EE
#     #----------------------------------------
#     while(abs(dE / EE) > tol):
#         FF.ConjugateGradients(1000)
#         dE = FF.Energy() - EE
#         EE = FF.Energy()
#     #--------------
#     FF.GetCoordinates(pybmol.OBMol)
#     #--------------
#     return pybmol

#--------------------------------------------------
def geomOptMM(pybmol, MMFF, tol):
    FF=pybel._forcefields[MMFF]
    FF.Setup(pybmol.OBMol)
    EE = FF.Energy()
    dE = EE
    while(abs(dE / EE) > tol):
        pybmol.localopt(forcefield=MMFF, steps=1000)
        dE = FF.Energy() - EE
        EE = FF.Energy()
    return pybmol

#--------------------------------------------------
def pybview(pybmol, pid):
    pybmol.write("pdb", "tmp"+"{:04d}".format(pid)+".pdb", overwrite=True)
    os.system("avogadro tmp"+"{:04d}".format(pid)+".pdb")
    os.remove("tmp"+"{:04d}".format(pid)+".pdb")

#--------------------------------------------------
def getRMSD(pybmol1, pybmol2):
    alg = openbabel.OBAlign(pybmol1.OBMol, pybmol2.OBMol)
    alg.Align()
    return alg.GetRMSD()

#--------------------------------------------------
def getCoords(pybmol):
    coords = []
    for atom in pybmol:
        coords.append( list(atom.coords) )
    return coords

#--------------------------------------------------
def getPybmol(pybmol, coords):
    molr = pybmol.clone
    for atom, coord in zip(molr, coords):
        atom.OBAtom.SetVector(coord[0], coord[1], coord[2])
    return molr


#################################################
#           main function start here            #
#################################################


#------------------------------------------------
#                 customize area                #
#------------------------------------------------
jobname = str(sys.argv[1])
#------------------------------------------------
rb1 = [int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])]     # dihedral idx
rb2 = [int(sys.argv[6]), int(sys.argv[7]), int(sys.argv[8]), int(sys.argv[9])]     # dihedral idx
#------------------------------------------------
MMFF       = "mmff94s"
QMFUNC     = 'B3LYP'
DISPERSION = 'd3'
QMBASIS    = '6-31G*'
TASK       = 'optimization'
#------------------------------------------------
MMtol = 1.0e-8
ertol = 1.0e-10
#------------------------------------------------
nrot = int(sys.argv[10])             # number of angular discret
#------------------------------------------------

#------------------------------------------------
#           initialize mpi parameters           #
#------------------------------------------------
nproc = MPI.COMM_WORLD.Get_size()
iproc = MPI.COMM_WORLD.Get_rank()
#------------------------------------------------

#------------------------------------------------
#         read the molecule with pybel          #
#------------------------------------------------
pybmol = pybel.readfile("pdb", jobname+".pdb").next()
#------------------------------------------------

#------------------------------------------------
#    geometry optimization MM using openbabel   #
#------------------------------------------------
pybmol = geomOptMM(pybmol, MMFF, MMtol)
#------------------------------------------------

#------------------------------------------------
mins_loc = []
cors_loc = []
#------------------------------------------------
diangle = numpy.linspace(0.0, 2*math.pi, nrot, endpoint=False)
diangle_loc = diangle[iproc::nproc]
#------------------------------------------------
for angle_i in diangle_loc:
#------------------------------------------------
    for angle_j in diangle:
    #--------------------------------------------
        molr = pybmol.clone
        molr.OBMol.SetTorsion(rb1[0],rb1[1],rb1[2],rb1[3], angle_i)
        molr.OBMol.SetTorsion(rb2[0],rb2[1],rb2[2],rb2[3], angle_j)
        molr = geomOptMM(molr, MMFF, MMtol)
        #--------------------------------------------
        print "MM finished: ", angle_i, angle_j
        #--------------------------------------------
        unique = True
        #--------------------------------------------
        for exmol in mins_loc:
            if (getRMSD(exmol, molr) < 0.25):
                unique = False
        if (unique == True):    
            mins_loc.append(molr)
            cors_loc.append(getCoords(molr))
        #--------------------------------------------

#------------------------------------------------
cors = MPI.COMM_WORLD.allgather(cors_loc)
#------------------------------------------------
mins = []
#------------------------------------------------
for i in range(0, nproc):
#------------------------------------------------
    for j in range(0, len(cors[i])):
    #--------------------------------------------
        molr = getPybmol(pybmol, cors[i][j])
        #----------------------------------------
        unique = True
        #----------------------------------------
        for exmol in mins:
            if (getRMSD(exmol, molr) < 0.25):
                unique = False
        if (unique == True):    
            mins.append(molr)
        #----------------------------------------

#------------------------------------------------
if (iproc == 0):
#------------------------------------------------
    f = open("PRMSD.dat", "w")
    #--------------------------------------------
    for i in range(0, len(mins)):
        for j in range(0, len(mins)):
            f.write("%7.2f" % (getRMSD(mins[i], mins[j])))
        f.write("\n")
    #--------------------------------------------
    f.close()
    #--------------------------------------------


#------------------------------------------------
dir_name = "qchem_opt_"+jobname+"_"+QMFUNC+"_"+DISPERSION+"_"+QMBASIS
#------------------------------------------------
if not os.path.isdir(dir_name):
    try:
        os.makedirs(dir_name)
    except Exception:
        pass
#------------------------------------------------



#-----------------------------------------
# quantum qchem
#-----------------------------------------
configId = range(0, len(mins))
configId_loc = configId[iproc::nproc]
energies_loc = []
#-----------------------------------------
for i in configId_loc:
    asemol = pyb2ase(mins[i], iproc)
    calc = QChem(xc=QMFUNC, 
                 disp=DISPERSION,
                 basis=QMBASIS,
                 task=TASK,
                 symmetry=False,
                 thresh=12,
                 scf_convergence=8,
                 maxfile=128,
                 mem_static=400,
                 mem_total=4000,
                 label="tmp_qchem"+"{:04d}".format(iproc)+"/qchem"+"{:04d}".format(i))
    asemol, E = calc.run(asemol)
    if ((asemol is not None) and (E is not None)):
        energies_loc.append((i,E))
        ase.io.write(dir_name+"/config_" + "{:04d}".format(i) + ".pdb", asemol)
        print "config %04d:    %15.7f\n" % (i, E)
    else:
        print "config %04d:    optimization failed\n" % (i)
#-----------------------------------------

#------------------------------------------------
energies = MPI.COMM_WORLD.allgather(energies_loc)
#------------------------------------------------
if (iproc == 0):
#------------------------------------------------
    f = open(dir_name+"/energies", "w")
    #--------------------------------------------
    for i in range(0, len(energies)):
        for j in range(0, len(energies[i])):
            f.write("config %04d:    %15.7f\n" % (energies[i][j][0], energies[i][j][1]))
    #--------------------------------------------
    f.close()
    #--------------------------------------------

MPI.COMM_WORLD.Barrier()

#-----------------------------------------
# show final molecule
#-----------------------------------------
# view(asemol, viewer='Avogadro')
#-----------------------------------------