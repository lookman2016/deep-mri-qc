import numpy as np
from scipy.spatial.distance import euclidean

import os, sys, time, csv, subprocess

import h5py
import sklearn

from sklearn.neighbors import KDTree

import nibabel as nib

from multiprocessing import Pool, Process


output_path = '/data1/data/ABIDE/'
cores = 10


def make_ibis(input_path, output_path, label_file):
    f = h5py.File(output_path + 'ibis.hdf5', 'w')

    pass_path = '~/T1_Minc_Pass/'
    fail_path = '~/T1_Minc_Fail/'

    #store a maximum number of "pass" images
    max_pass = 1000

    # First loop through the data we need to count the number of files
    # also check dims
    numImgs = 0
    x_dim, y_dim, z_dim = 0, 0, 0
    for root, dirs, files in os.walk(fail_path, topdown=False):
        for name in files:
            numImgs += 1
            if x_dim == 0:
               img =  nib.load(os.path.join(root, name)).get_data()
               print(np.shape(img))
               x_dim = np.shape(img)[0]
               y_dim = np.shape(img)[1]
               z_dim = np.shape(img)[2]
    for root, dirs, files in os.walk(pass_path, topdown=False):
        for name in files:
            numImgs += 1
            if numImgs > max_pass:
                break
        if numImgs > max_pass:
            break

    images    = f.create_dataset('T1', (numImgs, x_dim, y_dim, z_dim), dtype='float32')
    labels    = f.create_dataset('T1_QC_labels', (numImgs,2), dtype='bool')
    filenames = f.create_dataset('T1_filenames', (numImgs,), dtype='str')

    # Second time through, write the image data to the HDF5 file
    i = 0
    for root, dirs, files in os.walk(fail_path, topdown=False):
        for name in files:
            img = nib.load(os.path.join(root, name)).get_data()
            if np.shape(img) == (x_dim, y_dim, z_dim):
                images[i] = img
                labels[i] = [1, 0]
                filenames.append(os.path.join(root, name))
                i += 1


    for root, dirs, files in os.walk(pass_path, topdown=False):
        for name in files:
            img = nib.load(os.path.join(root, name)).get_data()
            if np.shape(img) == (x_dim, y_dim, z_dim):
                images[i] = img
                labels[i] = [0, 1]
                filenames.append(os.path.join(root, name))
                i += 1
            if i > max_pass:
                break
        if i > max_pass:
            break

    return

def make_nihpd(input_path, output_path, label_file):

  f = h5py.File(output_path + 'nihpd.hdf5', 'w')


def make_abide(path, label_file):
    patient_data = {}

    for index, filename in enumerate(os.listdir(path + '/T1_downsampled/')):
        if '.mnc' in filename:
            patient_id = filename[:-4]
            patient_data[patient_id] = {}

            print(filename, patient_id)
            patient_data[patient_id]['index'] = index
        else:
            index -= 1

    total_subjects = index + 1
    print('total of ', total_subjects, 'downsampled T1s')

    f = h5py.File(output_path + 'abide.hdf5', 'w')
    # f.create_dataset('images', (total_subjects, 181, 217, 181, 3), dtype='float32')  # t1, gradient magnitude, surface distance
    f.create_dataset('surfacepoints', (total_subjects, 40962*2, 3))
    # f.create_dataset('filenames', (total_subjects,), dtype=h5py.special_dtype(vlen=unicode))
    f.create_dataset('labels', (total_subjects,), dtype='bool')


    # load images and compute gradient
    # for filename in os.listdir(path + '/T1_downsampled/'):
    #     if '.mnc' in filename:
    #         patient_id = filename.split('.')[0]
    #
    #         i = patient_data[patient_id]['index']
    #         print(i, 'of', len(os.listdir(path + '/T1_downsampled/')))
    #
    #         img = nib.load(os.path.join(path + '/T1_downsampled/', filename)).get_data()  # load image data
    #
    #         f['images'][i, :, :, :, 0] = img
    #         f['images'][i, :, :, :, 1] = np.sum(np.gradient(img), axis=0)
    #     else:
    #         print(filename, 'should not be here')

    # extract surfaces from combined left/right surface objs
    for filename in os.listdir(path + '/surfaces/'):
        patient_id = filename.split('+')[1]

        i = patient_data[patient_id]['index']
        surface_obj = open(path + '/surfaces/' + filename)
        surface_obj.readlines(1) # first line is a header

        print('patient', i)

        for j, line in enumerate(surface_obj.readlines()):
            coords = line.split(" ")
            print('xyz coordinates', coords)
            if len(coords) != 3:
                break
            f['surfacespoints'][i, j, :] = [float(coords[0]) + 72.5, float(coords[1]) + 126.5,
                                            float(coords[2]) + 90.5]

        surface_obj.close()

    print("Reading QC labels...")
    label_file = open(os.path.join(path, label_file))
    lines = label_file.readlines()

    for i, line in enumerate(lines[1:]):   # skip header
        patient_id = line.split('+')[1].split('_')[0]
        label = int(line.split(',')[1])

        print('patient:', patient_id, 'label:', label, 'line: ', line)

        if not 'followup' in line and not 'anat_2' in line and not 'anat_3' in line and not 'anat_4' in line and not 'anat_5' in line and not 'anat_6' in line and not 'baseline' in line:
            patient_data[patient_id]['label'] = label

    print("Computing surface distances... Could take a while")

    # compute surface distance volumes in same space as T1
    p = Pool(cores)
    surf_points = np.zeros((40962*2, 3), dtype='float32')

    for i in range(total_subjects):
        surf_points = f['surfacepoints'][i, :, :]

        # p.apply_async(distance_to_surf, args=(surf_points, i,))
        distance_to_surf(surf_points, i)
        print("Launched job", i)

    p.close()
    p.join()

    print("Done ", total_subjects, 'surfaces')

    f.close()

    return 0

def distance_to_surf(surface_points, patient_id):
    surface_distance = np.ones((181, 217, 181), dtype='float32')

    print("surface points: ", np.shape(surface_points))

    floatX = np.zeros(np.shape(surface_distance)[0], dtype='float32')
    floatY = np.zeros(np.shape(surface_distance)[1], dtype='float32')
    floatZ = np.zeros(np.shape(surface_distance)[2], dtype='float32')

    for xx in range(np.shape(floatX)[0]):
        floatX[xx] = float(xx)

    for yy in range(np.shape(floatY)[0]):
        floatY[yy] = float(yy)

    for zz in range(np.shape(floatZ)[0]):
        floatZ[zz] = float(zz)

    print("building KDTree...")
    tree = KDTree(surface_points, leaf_size=10000)
    print("built KDTree!")

    for z in range(np.shape(surface_distance)[0]):
        print("z: ", z)
        for y in range(np.shape(surface_distance)[1]):
            for x in range(np.shape(surface_distance)[2]):
                (distance, index) = tree.query(np.reshape([floatZ[z], floatY[y], floatX[x]], (1, 3)), return_distance = True)
                surface_distance[z, y, x] = distance
                # brute force method, very slow
                # for point in surf_points:
                #     d = euclidean([floatZ[z], floatY[y], floatX[x]], point)

                #     if surface_distance[z,y,x] > d:
                #         surface_distance[z,y,x] = d

    output_filename = os.path.join(output_path, str(patient_id) + '_surface_distance.nii.gz')
    img = nib.Nifti1Image(surface_distance, np.eye(4))

    nib.save(img, output_filename)
    return surface_distance, output_filename


def combine_objs(obj1, obj2, newname):
    print(obj1)
    print(obj2)
    print(newname)
    subprocess.Popen(['objconcat', obj1, obj2, 'none', 'none', newname, 'none'])



if __name__ == "__main__":
    path = '/data1/data/ABIDE/'

    # for filename in os.listdir(path + '/surfaces/'):
    #     if "right" in filename:
    #         # patient_id = filename.split('+')[1]
    #
    #         filename1 = filename
    #         filename2 = filename.replace("right", "left")
    #         filename3 = filename.replace("right", "combined")
    #
    #         combine_objs(os.path.join(path, 'surfaces/' + filename1), os.path.join(path, 'surfaces/' + filename2), os.path.join(path, 'surfaces/' + filename3))

    # for filename in os.listdir(path + '/T1s/'):
    #     try:
    #         patient_id = filename.split('+')[1]
    #
    #         p = subprocess.Popen(['mincresample', '-nearest_neighbour', '-like', path + 'icbm_template_1.00mm.mnc', path + 'T1s/' + filename, path + 'T1_downsampled/' + patient_id + '.mnc', '-clobber'])
    #         p.communicate()
    #     except:
    #         print filename



    make_abide('/data1/data/ABIDE/', 'labels.csv')
  # make_nihpd('/data1/data/NIHPD/assembly/', 'data1/data/dl-datasets/')
