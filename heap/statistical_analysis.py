#!/usr/bin/python
"""Statistical analyses simulation data from logfiles with ipyvolume

Attributes:
    clock_freq (float): Clock frequency
    clock_rate (float): Clock rate
    colors (np-array of floats): Colors fish depending on their location
    fig (figure object): ipv figure
    fishes (int): Number of simulated fishes
    phi (float): Orientation angles
    timesteps (TYPE): Description
    x (float): x-positions
    y (float): y-positions
    z (float): z-positions
"""
import json
import os
import sys
import glob
import math
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import cm
from scipy.spatial import ConvexHull, convex_hull_plot_2d
from scipy.spatial.distance import cdist
from scipy.optimize import linear_sum_assignment

def init_log_stat():
    print('creating stat logfile')
    with open('./logfiles/{}_stat.csv'.format(loopname), 'w') as f:
        f.truncate()
        f.write('filename, no_fish, escape_angle [rad], n_magnitude, surface_reflections, speed_ratio, phi_std_init, phi_std_end, hull_area_max [m^2], eaten, no_tracks_avg, kf tracking error avg [mm] \n')


def log_stat(loopname, filename, fishes, escape_angle, noise, surface_reflections, speed_ratio, phi_std_init, phi_std_end, hull_area_max, eaten, no_tracks_avg, tracking_error_avg):
    """Logs the meta data of the experiment
    """
    with open('./logfiles/{}_stat.csv'.format(loopname), 'a+') as f:
        f.write(
            '{}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}\n'.format( #add: escape_angle, reflection on/off, speed ratio pred/fish, tracking error: how to measure?? dist track - closest groundtruth?
                filename,
                fishes,
                escape_angle,
                noise,
                surface_reflections,
                speed_ratio,
                phi_std_init,
                phi_std_end,
                hull_area_max,
                eaten,
                no_tracks_avg,
                tracking_error_avg
            )
        )


# Load Data
try:
    filename = sys.argv[1]
except:
    list_dir = glob.glob('logfiles/*.txt')
    filename = sorted(list_dir)[-1][9:-9]
    print('filename not specified! automatically choosing newest file:', filename)
try:
    data = np.loadtxt('./logfiles/{}_data.txt'.format(filename), delimiter=',')
    with open('./logfiles/{}_meta.txt'.format(filename), 'r') as f:
        meta = json.loads(f.read())
except:
    print('Data file with prefix {} does not exist.\nProvide prefix of data you want to plot in format yymmdd_hhmmss as command line argument, e.g.:\n >python animation.py 201005_111211'.format(filename))
    sys.exit()


# Read Experimental Parameters
clock_freq = meta['Clock frequency [Hz]']
clock_rate = 1000/clock_freq # [ms]
arena = meta['Arena [mm]']
timesteps = data.shape[0]
n_magnitude = meta['Visual noise magnitude [% of distance]']
fishes = meta['Number of fishes']
escape_angle = meta['escape_angle']
surface_reflections = meta['surface_reflections']
pred_speed = meta['pred_speed']
pred_bool = meta['pred_bool']


if 'loopname' in meta:
    loopname = meta['loopname']
else:
    loopname = filename#'no_loop'

#start logging
if not os.path.isfile('./logfiles/{}_stat.csv'.format(loopname)):
    init_log_stat()

#phi std, mean
phi_mean_cos = np.zeros((timesteps))
phi_mean_sin = np.zeros((timesteps))

for ii in range(fishes):
    phi_mean_cos += np.cos(data[:, 4*ii + 3])
    phi_mean_sin += np.sin(data[:, 4*ii + 3])

phi_mean_cos = phi_mean_cos/fishes
phi_mean_sin = phi_mean_sin/fishes
phi_mean = np.arctan2(phi_mean_sin, phi_mean_cos)
phi_std = np.sqrt(-np.log(phi_mean_sin**2 + phi_mean_cos**2))

print('The initial std phi is {0:.1f}rad.'.format(phi_std[0]))
print('The final std phi is {0:.1f}rad.'.format(phi_std[-1]))
print('The difference of mean phi is {0:.1f}rad.'.format(phi_mean[-1] - phi_mean[0]))

#check eating area: ellipse
eaten = []
speed_ratio = []
if pred_bool:
    pred_pos = data[:, 8*fishes : 8*fishes + 4]
    
    for ii in range(fishes):
        a = 60 #semi-major axis in x
        b = 50 #semi-minor axis in y
        rel_pos = data[:, 4*ii :  4*ii + 3] - pred_pos[:, 0 : 3]
        rel_pos_rot = np.empty((timesteps, 2))
        rel_pos_rot[:, 0] = np.cos(pred_pos[:, 3])*rel_pos[:, 0] - np.sin(pred_pos[:, 3])*rel_pos[:, 1]
        rel_pos_rot[:, 1] = np.sin(pred_pos[:, 3])*rel_pos[:, 0] + np.cos(pred_pos[:, 3])*rel_pos[:, 1]
        p = ((rel_pos[:, 0])**2 / a**2 +  (rel_pos[:, 1])**2 / b**2)
        eaten.append(np.any(p < 1)) #and consider delta z !
    
    print('{} fish out of {} got eaten.'.format(sum(eaten), fishes))
    
    #check pred_speed
    v_max_avg = 0
    for ii in range(fishes):
        v_xy = np.sqrt(data[:, 4*(ii+fishes)]**2 + data[:, 4*(ii+fishes) + 1]**2)
        v_max = max(v_xy)
        v_max_avg += v_max
    
    v_max_avg /= fishes
    speed_ratio = pred_speed/v_max_avg
    print('The avg pred to fish speed ratio is {}.'.format(speed_ratio))

#calc ConvexHull
hull_area_max = 0
for i in range(timesteps):
    points = np.array([data[i, 4*ii :  4*ii + 2] for ii in range(fishes)])  # no_fish x 2
    hull = ConvexHull(points)
    if hull.volume > hull_area_max:
        hull_area_max = hull.volume

print('The largest hull area is {} m^2.'.format(hull_area_max/1000**2))

#log kf data¨
no_tracks_avg = 0
tracking_error_avg = 0   
for protagonist_id in range(fishes):
    data_kf = np.genfromtxt('./logfiles/kf_{}.csv'.format(protagonist_id), delimiter=',')
    data_kf = data_kf[1:,:] #cut title row
    #no tracks
    tracks = np.unique(data_kf[:,0]).astype(int)
    no_tracks = len(tracks) - pred_bool
    no_tracks_avg += no_tracks
    #tracking   
    kf_iterations = np.unique(data_kf[:,1]).astype(int)
    for i in range(timesteps):#kf_iterations: #all iterations
        kf_pos = data_kf[np.argwhere(data_kf[:,1] == i).ravel(), 2:5] #no_fishx3
        if np.size(kf_pos, 0):
            prot_pos = data[i, 4*protagonist_id :  4*protagonist_id + 3] 
            prot_phi = data[i, 4*protagonist_id + 3 :  4*protagonist_id + 4] 
            all_fish_pos = np.array([data[i, 4*ii :  4*ii + 3] for ii in range(fishes) if ii != protagonist_id]) #for matching only us pos, no phi
            rel_pos_unrot = prot_pos - all_fish_pos

            R = np.array([[math.cos(prot_phi), math.sin(prot_phi), 0],[-math.sin(prot_phi), math.cos(prot_phi), 0],[0,0,1]]) #rotate by phi around z axis to transform from global to robot frame
            groundtruth_pos =  (R @ rel_pos_unrot.T).T
            
            dist = cdist(kf_pos, groundtruth_pos, 'euclidean')    
            kf_matched_ind, groundtruth_matched_ind = linear_sum_assignment(dist)
            error_i = dist[kf_matched_ind, groundtruth_matched_ind].sum()
            tracking_error_avg += error_i/np.size(kf_pos, 0)

no_tracks_avg /= fishes
print('{} kf tracks were created in avg.'.format(no_tracks_avg))


tracking_error_avg /= (timesteps*fishes)
print('The avg tracking error is {} mm.'.format(tracking_error_avg))

log_stat(loopname, filename, fishes, escape_angle, n_magnitude, surface_reflections, speed_ratio, phi_std[0], phi_std[-1], hull_area_max/1000**2, int(sum(eaten)), no_tracks_avg, tracking_error_avg)