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
from utils import *
#--------------------------------------------------



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
QMFUNC     = 'RIMP2'
DISPERSION = 'None'
QMBASIS    = 'aug-cc-pVDZ'
TASK       = 'optimization'
#------------------------------------------------
MMtol = 1.0e-8
QMtol = 4.5e-3
ertol = 1.0e-10
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
pybmol = next(pybel.readfile("pdb", jobname+".pdb"))
#------------------------------------------------

#------------------------------------------------
if (jobname   == "path_1001"):
    rotlist = numpy.array([[  0,360], [ 35,310], [ 95,275], [135,240], [180,213], [199,150], [247,102], [318, 78]])
    cfglist = numpy.array([     "LM",      "TS",      "LM",      "TS",      "LM",      "TS",      "LM",      "TS"])
elif (jobname == "path_1101"):
    rotlist = numpy.array([[  0,360], [ 65,310], [ 78,250], [178,195], [225,148], [252, 90], [310, 70], 
                           [358,190], [ 45,135], [100, 90], [120, 65], [182,  3], [240,315], [295,240]])
    cfglist = numpy.array([     "LM",      "TS",      "TS",      "LM",      "TS",      "LM",      "TS",
                                "LM",      "TS",      "LM",      "TS",      "LM",      "TS",      "TS"])
elif (jobname == "path_1111"):
    rotlist = numpy.array([[  0,360], [ 62,325], [ 85,255], [130,200], [185,195], [230,160], [257, 92], [298, 40]])
elif (jobname == "path_10n01"):
    rotlist = numpy.array([[  0,360], [ 44,302], [ 90,245], [150,198], [176,180], [198,153], [248, 87], [302, 43]])
elif (jobname == "path_11n01"):
    rotlist = numpy.array([[  0,360], [108,253], [230,130], [293, 72], [  0,190], [118, 72], [212,335], [288,255]])
elif (jobname == "path_11n11"):
    rotlist = numpy.array([[  0,360], [ 40,313], [ 75,268], [133,226], [187,185], [223,136], [265, 77], [310, 46]])
#------------------------------------------------
rotlist = rotlist / 360.0 * (2*math.pi)
#------------------------------------------------
diangles = []
constrns = []
#------------------------------------------------
for i in range(0, len(rotlist)):
#------------------------------------------------
    diangles.append([rotlist[i,0], rotlist[i,1]])
#------------------------------------------------
diangles_loc = diangles[iproc::nproc]
#------------------------------------------------

#------------------------------------------------
dir_name = "qchem_"+jobname+"_"+QMFUNC+"_"+DISPERSION+"_"+QMBASIS
#------------------------------------------------
if not os.path.isdir(dir_name):
    try:
        os.makedirs(dir_name)
    except Exception:
        pass
#------------------------------------------------

#------------------------------------------------
#    constrained optimization QM using qchem    #
#------------------------------------------------
energies_loc = []
#------------------------------------------------
for diangle in diangles_loc:
    #----------------------------------------
    angle_i = pybmol.OBMol.GetTorsion(rb1[0],rb1[1],rb1[2],rb1[3])/360*(2*math.pi) + diangle[0]
    angle_j = pybmol.OBMol.GetTorsion(rb2[0],rb2[1],rb2[2],rb2[3])/360*(2*math.pi) + diangle[1]
    #----------------------------------------
    molr = pybmol.clone
    molr.OBMol.SetTorsion(rb1[0],rb1[1],rb1[2],rb1[3], angle_i)
    molr.OBMol.SetTorsion(rb2[0],rb2[1],rb2[2],rb2[3], angle_j)
    molr = geomOptMM(molr, [[rb1, angle_i],[rb2, angle_j]], MMFF, MMtol)
    #----------------------------------------
    asemol = pyb2ase(molr, iproc)
    #----------------------------------------
    prefix = "theta1_"+"{:5.3f}".format(diangle[0])+"_theta2_"+"{:5.3f}".format(diangle[1])
    #----------------------------------------
    calc = QChem(xc=QMFUNC, 
                 disp=DISPERSION,
                 basis=QMBASIS,
                 task=TASK,
                 symmetry=False,
                 tcs=[[rb1, angle_i],[rb2,angle_j]],
                 opt_maxcycle=200,
                 thresh=12,
                 scf_convergence=8,
                 maxfile=128,
                 mem_static=400,
                 mem_total=4000,
                 label="tmp_qchem"+"{:04d}".format(iproc)+"/" + prefix)
    asemol, E = calc.run(asemol)
    #----------------------------------------
    if ((asemol is not None) and (E is not None)):
        energies_loc.append((diangle[0], diangle[1], E))
        ase.io.write(dir_name+"/" + prefix +".pdb", asemol)
        print("theta1: %5.3f,  theta2: %5.3f,  energy: %15.7f" % (diangle[0], diangle[1], E))
        sys.stdout.flush()
    else:
        print("theta1: %5.3f,  theta2: %5.3f,  optimization failed" % (diangle[0], diangle[1]))
        sys.stdout.flush()
    #----------------------------------------

#------------------------------------------------
energies = MPI.COMM_WORLD.allgather(energies_loc)
energies = sum(energies, []) # flatten 2d array to 1d
energies.sort()
#------------------------------------------------
if (iproc == 0):
#------------------------------------------------
    f = open(dir_name+"/energies", "w")
    #--------------------------------------------
    for i in range(0, len(energies)):
        f.write("%5.3f  %5.3f  %15.7f\n" % (energies[i][0], energies[i][1], energies[i][2]))
    #--------------------------------------------
    f.close()
    #--------------------------------------------

#------------------------------------------------
MPI.COMM_WORLD.Barrier()
#------------------------------------------------