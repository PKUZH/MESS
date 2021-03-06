""" Associate MESS detections
"""
import os, glob
from obspy import UTCDateTime
import numpy as np
import multiprocessing as mp
import config
import warnings
warnings.filterwarnings("ignore")


# assoc det
def assoc_one_day(start_date, start_evid):
    print('associating %s'%start_date)
    print('reading detection phase file')
    det_list = read_det_pha(det_pha, start_date, start_date+86400)
    det_list = det_list[[temp_id in temp_loc_dict for temp_id in det_list['temp_id']]]
    out_dt = open('input/dt_%s.cc'%start_date.date,'w')
    out_event = open('input/event_%s.dat'%start_date.date,'w')
    dets = det_list[(det_list['ot']>start_date)*(det_list['ot']<start_date+86400)]
    dets = dets[dets['cc']>cc_thres]
    num_dets = len(dets)
    for i in range(num_dets):
        if i%500==0: print('{} events associated | left {}'.format(i, len(dets)))
        det_id = start_evid + i
        det_0 = dets[0]
        # find neighbor dets by ot cluster
        cond_ot = abs(dets['ot']-det_0['ot']) < ot_dev
        dets_reloc = dets[cond_ot]
        cc = dets_reloc['cc']
        # whether self-det
        is_self = False
        for j,det in enumerate(dets_reloc):
            temp_loc = temp_loc_dict[det['temp_id']]
            if abs(temp_loc[0]-det['ot'])<ot_dev: 
                det_i = det
                det_id = det['temp_id']
                is_self = True
                dets_reloc = np.delete(dets_reloc, j, axis=0)
                cc = np.delete(cc, j, axis=0)
                break
        # sort by cc & restrict number of neighbor
        if not is_self: det_i = dets_reloc[np.argmax(cc)]
        if len(cc)>0:
            cc_min = np.sort(cc)[::-1][0:nbr_thres[1]][-1]
            cc_max = np.amax(cc)
            dets_reloc = dets_reloc[cc>=cc_min]
            cc = cc[cc>=cc_min]
        # replace temp_loc with reloc
        if not is_self: temp_loc = temp_loc_dict[det_i['temp_id']]
        det_loc = [det_i['ot']] + temp_loc[1:] + [calc_mag(det_i)]
        # write dt.cc & event.dat
        if len(dets_reloc)>=nbr_thres[0] or is_self:
            for det in dets_reloc: write_dt(det, det_id, det['ot']-det_loc[0], out_dt)
            write_event(det_loc, det_id, out_event)
        # next det
        dets = np.delete(dets, np.where(cond_ot), axis=0)
        if len(dets)==0: break
    out_dt.close()
    out_event.close()


# read temp pha --> temp_loc_dict
def read_temp_pha(temp_pha):
    f=open(temp_pha); lines=f.readlines(); f.close()
    temp_loc_dict = {}
    for line in lines:
        codes = line.split(',')
        if len(codes[0])<14: continue
        ot = UTCDateTime(codes[0])
        lat, lon, dep = [float(code) for code in codes[1:4]]
        temp_id = codes[-1][:-1]
        temp_loc_dict[temp_id] = [ot, lat, lon, dep]
    return temp_loc_dict


# read det pha (MESS output) --> det_list
def read_det_pha(det_pha, start_time, end_time):
    f=open(det_pha); lines=f.readlines(); f.close()
    dtype = [('temp_id','O'),('ot','O'),('loc','O'),('cc','O'),('picks','O')]
    det_list = []
    for line in lines:
        codes = line.split(',')
        if len(codes[0])>=14:
            temp_id = codes[0].split('_')[0]
            ot = UTCDateTime(codes[1])
            lat, lon, dep, cc_det = [float(code) for code in codes[2:6]]
            to_add = True if start_time<ot<end_time else False
            if to_add: det_list.append((temp_id, ot, [lat, lon, dep], cc_det, {}))
        else:
            if not to_add: continue
            net_sta = codes[0]
            dt_p, dt_s, s_amp, cc_p, cc_s = [float(code) for code in codes[3:8]]
            det_list[-1][-1][net_sta] = [dt_p, dt_s, s_amp, cc_p, cc_s]
    return np.array(det_list, dtype=dtype)


# write dt.cc
def write_dt(det, evid, ot_corr, fout):
    temp_id = det['temp_id']
    fout.write('# {:9} {:9} 0.0\n'.format(evid, temp_id))
    for net_sta, [dt_p, dt_s, _, cc_p, cc_s] in det['picks'].items():
        sta = net_sta.split('.')[1]
        if abs(dt_p)<=dt_thres[0] and cc_p>=cc_thres: fout.write('{:7} {:8.5f} {:.4f} P\n'.format(sta, dt_p+ot_corr, cc_p**0.5))
        if abs(dt_s)<=dt_thres[1] and cc_s>=cc_thres: fout.write('{:7} {:8.5f} {:.4f} S\n'.format(sta, dt_s+ot_corr, cc_s**0.5))


# write event.dat
def write_event(event_loc, evid, fout):
    ot, lat, lon, dep, mag = event_loc
    dep += dep_corr
    date = '{:0>4}{:0>2}{:0>2}'.format(ot.year, ot.month, ot.day)
    time = '{:0>2}{:0>2}{:0>2}{:0>2.0f}'.format(ot.hour, ot.minute, ot.second, ot.microsecond/1e4)
    loc = '{:7.4f}   {:8.4f}   {:8.3f}  {:4.1f}'.format(lat, lon, dep, mag)
    err_rms = '   0.00    0.00   0.0'
    fout.write('{}  {}   {} {} {:>10}\n'.format(date, time, loc, err_rms, evid))


# calc mag with PAD assoc
def calc_mag(event):
    event_loc = {'evt_lat':event['loc'][0], 'evt_lon':event['loc'][1]}
    event_pick = np.array([(net_sta, s_amp) \
        for net_sta, [_,_,s_amp,_,_] in event['picks'].items()],
        dtype=[('net_sta','O'),('s_amp','O')])
    event_loc = pad_calc_mag(event_pick, event_loc)
    return event_loc['mag']


if __name__ == '__main__':
  # i/o paths
  cfg = config.Config()
  dep_corr = cfg.dep_corr
  temp_pha = cfg.temp_pha
  det_pha = cfg.det_pha
  for fname in glob.glob('input/dt_*.cc'): os.unlink(fname)
  for fname in glob.glob('input/event_*.dat'): os.unlink(fname)
  # assoc params
  ot_dev = cfg.ot_dev
  cc_thres = cfg.cc_thres
  dt_thres = cfg.dt_thres
  nbr_thres = cfg.nbr_thres
  evid_stride = cfg.evid_stride
  num_workers = cfg.num_workers
  time_range = cfg.time_range
  start_date, end_date = [UTCDateTime(date) for date in cfg.time_range.split('-')]
  num_days = (end_date.date - start_date.date).days
  pad_calc_mag = cfg.calc_mag
  # read phase file
  print('reading template phase file')
  temp_loc_dict = read_temp_pha(temp_pha)
  # start assoc
#  for day_idx in range(num_days): assoc_one_day(start_date+86400*day_idx, evid_stride*(1+day_idx))
  pool = mp.Pool(num_workers)
  for day_idx in range(num_days):
    pool.apply_async(assoc_one_day, args=(start_date+86400*day_idx, evid_stride*(1+day_idx),))
  pool.close()
  pool.join()
  # merge files
  os.system('cat input/dt_*.cc > input/dt.cc')
  os.system('cat input/event_*.dat > input/event.dat')
  for fname in glob.glob('input/dt_*.cc'): os.unlink(fname)
  for fname in glob.glob('input/event_*.dat'): os.unlink(fname)
  
