%  create a channel map file

Nchannels = 32;
connected = true(Nchannels, 1);
chanMap   = 1:Nchannels;
chanMap0ind = chanMap - 1;
xcoords   = ones(Nchannels,1);
ycoords   = [1:Nchannels]';
kcoords   = ones(Nchannels,1); % grouping of channels (i.e. tetrode groups)

fs = 25000; % sampling frequency
save('C:\DATA\Spikes\20150601_chan32_4_900s\chanMap.mat', ...
    'chanMap','connected', 'xcoords', 'ycoords', 'kcoords', 'chanMap0ind', 'fs')

%%

Nchannels = 32;
connected = true(Nchannels, 1);
chanMap   = 1:Nchannels;
chanMap0ind = chanMap - 1;

xcoords   = repmat([1 2 3 4]', 1, Nchannels/4);
xcoords   = xcoords(:);
ycoords   = repmat(1:Nchannels/4, 4, 1);
ycoords   = ycoords(:);
kcoords   = ones(Nchannels,1); % grouping of channels (i.e. tetrode groups)

fs = 25000; % sampling frequency

save('C:\DATA\Spikes\Piroska\chanMap.mat', ...
    'chanMap','connected', 'xcoords', 'ycoords', 'kcoords', 'chanMap0ind', 'fs')
%%

% kcoords is used to forcefully restrict templates to channels in the same
% channel group. An option can be set in the master_file to allow a fraction 
% of all templates to span more channel groups, so that they can capture shared 
% noise across all channels. This option is

% ops.criterionNoiseChannels = 0.2; 

% if this number is less than 1, it will be treated as a fraction of the total number of clusters

% if this number is larger than 1, it will be treated as the "effective
% number" of channel groups at which to set the threshold. So if a template
% occupies more than this many channel groups, it will not be restricted to
% a single channel group. 

%% Example: dual-sided / 3-D probe with zcoords
%
% For probes that have recording sites on two faces (or any geometry with a
% meaningful z-component) you can now include a 'zcoords' variable in the
% chanMap.mat file.  KiloSort will use the full 3-D Euclidean distance for:
%   - local whitening neighbourhood (whiteningLocal)
%   - drift-correction channel covariance (clusterAndDriftCorrection)
%   - spatial interpolation kernel (shift_matrix / shift_data)
%
% When exporting to Phy (rezToPhy), the 3-D positions are projected to 2-D
% as:  xcoords_2d = xcoords + zcoords
%      ycoords_2d = ycoords
% This horizontally separates shanks by their z-depth so Phy's channel
% map viewer shows each face as a distinct column.
%
% If 'zcoords' is absent, KiloSort falls back to all-zeros (2-D behaviour).

Nchannels = 64;                     % 32 sites per face
connected = true(Nchannels, 1);
chanMap   = 1:Nchannels;
chanMap0ind = chanMap - 1;
kcoords   = ones(Nchannels, 1);

% Face A (z = 0 µm): sites 1–32
xcoords_A = repmat([0 16]', 16, 1);        % two columns, 16 µm apart
ycoords_A = sort(repmat((0:15)*20, 1, 2)');  % 20 µm pitch along shank
zcoords_A = zeros(32, 1);                   % face A is at z = 0

% Face B (z = 25 µm): sites 33–64
xcoords_B = repmat([0 16]', 16, 1);
ycoords_B = sort(repmat((0:15)*20, 1, 2)');
zcoords_B = 25 * ones(32, 1);              % face B is at z = 25 µm

xcoords = [xcoords_A; xcoords_B];
ycoords = [ycoords_A; ycoords_B];
zcoords = [zcoords_A; zcoords_B];

fs = 30000;
save('/path/to/chanMap_dual_sided.mat', ...
    'chanMap', 'connected', 'xcoords', 'ycoords', 'zcoords', ...
    'kcoords', 'chanMap0ind', 'fs')