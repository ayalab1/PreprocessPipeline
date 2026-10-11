
function [spikeTimes, clusterIDs, amplitudes, templates, templateFeatures, ...
    templateFeatureInds, pcFeatures, pcFeatureInds] = rezToPhy(rez, savePath)
% pull out results from kilosort's rez to either return to workspace or to
% save in the appropriate format for the phy GUI to run on. If you provide
% a savePath it should be a folder, and you will need to have npy-matlab
% available (https://github.com/kwikteam/npy-matlab)
%
% spikeTimes will be in samples, not seconds


outputs = {'amplitudes.npy', 'channel_map.npy', 'channel_positions.npy', 'pc_features.npy', ...
           'pc_feature_ind.npy', 'similar_templates.npy', 'spike_clusters.npy', 'spike_templates.npy', ...
           'spike_times.npy', 'templates.npy', 'templates_ind.npy', 'template_features.npy', ...
           'template_feature_ind.npy', 'whitening_mat.npy', 'whitening_mat_inv.npy'};

fs = dir(fullfile(savePath, '*.npy'));
for i = 1:length(fs)
    fname = fs(i).name;
    % don't delete .npy files which have nothing to do with us
    if find(strcmp(fname, outputs))
        delete(fullfile(savePath, fname));
    end
end
if exist(fullfile(savePath, '.phy'), 'dir')
    rmdir(fullfile(savePath, '.phy'), 's');
end

spikeTimes = uint64(rez.st3(:,1));
% [spikeTimes, ii] = sort(spikeTimes);
spikeTemplates = uint32(rez.st3(:,2));
if size(rez.st3,2)>4
    spikeClusters = uint32(1+rez.st3(:,5));
end
amplitudes = rez.st3(:,3);

Nchan = rez.ops.Nchan;

% try
%     load(rez.ops.chanMap);
% catch
%    chanMap0ind  = [0:Nchan-1]';
%    connected    = ones(Nchan, 1);
%    xcoords      = ones(Nchan, 1);
%    ycoords      = (1:Nchan)';
% end
% chanMap0 = chanMap(connected>1e-6);

connected   = rez.connected(:);
xcoords     = rez.xcoords(:);
ycoords     = rez.ycoords(:);
% zcoords: present for 3-D probes (e.g. double-sided shanks), else zeros
if isfield(rez, 'zcoords')
    zcoords = rez.zcoords(:);
else
    zcoords = zeros(size(xcoords));
end
chanMap     = rez.ops.chanMap(:);
chanMap0ind = chanMap - 1;

nt0 = size(rez.W,1);
U = rez.U;
W = rez.W;

% for i = 1:length(chanMap0)
%     chanMap0(i) = chanMap0(i) - sum(chanMap0(i) > chanMap(connected<1e-6));
% end
% [~, invchanMap0] = sort(chanMap0);

templates = zeros(Nchan, nt0, rez.ops.Nfilt, 'single');
for iNN = 1:rez.ops.Nfilt
   templates(:,:,iNN) = squeeze(U(:,iNN,:)) * squeeze(W(:,iNN,:))'; 
end
templates = permute(templates, [3 2 1]); % now it's nTemplates x nSamples x nChannels
templatesInds = repmat([0:size(templates,3)-1], size(templates,1), 1); % we include all channels so this is trivial

templateFeatures = rez.cProj;
templateFeatureInds = uint32(rez.iNeigh);
pcFeatures = rez.cProjPC;
pcFeatureInds = uint32(rez.iNeighPC);

if ~isempty(savePath)
    
    writeNPY(spikeTimes, fullfile(savePath, 'spike_times.npy'));
    writeNPY(uint32(spikeTemplates-1), fullfile(savePath, 'spike_templates.npy')); % -1 for zero indexing
    if size(rez.st3,2)>4
        writeNPY(int32(spikeClusters-1), fullfile(savePath, 'spike_clusters.npy')); % -1 for zero indexing
    else
        writeNPY(int32(spikeTemplates-1), fullfile(savePath, 'spike_clusters.npy')); % -1 for zero indexing
    end
    writeNPY(amplitudes, fullfile(savePath, 'amplitudes.npy'));
    writeNPY(templates, fullfile(savePath, 'templates.npy'));
    writeNPY(templatesInds, fullfile(savePath, 'templates_ind.npy'));
    
%     Fs = rez.ops.fs;
    conn        = logical(connected);
    chanMap0ind = int32(chanMap0ind);
    
    writeNPY(chanMap0ind(conn), fullfile(savePath, 'channel_map.npy'));
    % Project 3-D geometry to 2-D for Phy's channel map viewer.
    % Baseline: xcoords_2d = xcoords + zcoords, which shifts each shank
    % horizontally by its z-depth so they don't overlap in Phy.
    % For 2-D probes zcoords is all-zeros so this is a no-op.
    %
    % Additional correction for double-sided shanks (detected via rez.sidecoords):
    %   side 0 (first appearing in chanMap) -> mean(xcoords of that side)
    %   side 1 (second side)               -> side-0 x + 0.5 * inter-shank distance
    % Inter-shank distance is computed per adjacent shank pair (varies across probes).
    % Edge case: last shank reuses the spacing from the previous shank pair.

    % Step 1: baseline 2-D projection (restores correct shank x-separation for
    % all probes including single-sided 3-D ones; no-op for 2-D probes).
    xcoords_2d = xcoords + zcoords;

    % Step 2: side-aware x correction for double-sided shanks (optional).
    % xc is filtered to Nchan via (conn); sc/kc come from rez fields that
    % preprocessData.m already filtered to Nchan – do NOT re-index with conn.
    if any(zcoords(conn) ~= 0) && isfield(rez, 'sidecoords') && isfield(rez.ops, 'kcoords')
        xc = xcoords_2d(conn);  % working copy – Nchan (connected channels only)
        % NOTE: rez.sidecoords and rez.ops.kcoords are already Nchan-length
        % (filtered by preprocessData.m), so do NOT index them with conn.
        sc = rez.sidecoords(:);
        kc = rez.ops.kcoords(:);

        % Unique shanks in first-appearance order
        [~, firstIdx] = unique(kc, 'first');
        [~, sortOrd]  = sort(firstIdx);
        uShanks = unique(kc);
        uShanks = uShanks(sortOrd);

        % Pass 1: representative x per shank (mean of first-appearing side)
        shankX = nan(numel(uShanks), 1);
        for si = 1:numel(uShanks)
            shMask  = kc == uShanks(si);
            uSides  = unique(sc(shMask));
            if numel(uSides) == 2
                firstSide = sc(find(shMask, 1));
                shankX(si) = mean(xc(shMask & (sc == firstSide)));
            else
                shankX(si) = mean(xc(shMask));
            end
        end

        % Pass 2: offset the second face of each double-sided shank
        prevHalfDist = NaN;
        for si = 1:numel(uShanks)
            shMask = kc == uShanks(si);
            uSides = unique(sc(shMask));

            if numel(uSides) ~= 2
                % Single-sided – update spacing tracker and move on
                if si < numel(uShanks)
                    prevHalfDist = abs(shankX(si+1) - shankX(si)) / 2;
                end
                continue;
            end

            % Determine half inter-shank distance for this shank
            if si < numel(uShanks)
                halfDist = abs(shankX(si+1) - shankX(si)) / 2;
                prevHalfDist = halfDist;
            elseif ~isnan(prevHalfDist)
                halfDist = prevHalfDist;  % last shank: reuse previous spacing
            else
                warning('rezToPhy: last shank is double-sided but no previous inter-shank distance available; x-offset skipped.');
                continue;  % keep the baseline x + z projection for this shank
            end

            firstSide  = sc(find(shMask, 1));
            secondSide = uSides(uSides ~= firstSide);
            side0 = shMask & (sc == firstSide);
            side1 = shMask & (sc == secondSide);
            x0 = mean(xc(side0));
            xc(side0) = x0;
            xc(side1) = x0 + halfDist;
        end

        xcoords_2d(conn) = xc;  % write corrected positions back
    end
    ycoords_2d = ycoords;
    writeNPY([xcoords_2d(conn) ycoords_2d(conn)], fullfile(savePath, 'channel_positions.npy'));
    
    writeNPY(templateFeatures, fullfile(savePath, 'template_features.npy'));
    writeNPY(templateFeatureInds'-1, fullfile(savePath, 'template_feature_ind.npy'));% -1 for zero indexing
    writeNPY(pcFeatures, fullfile(savePath, 'pc_features.npy'));
    writeNPY(pcFeatureInds'-1, fullfile(savePath, 'pc_feature_ind.npy'));% -1 for zero indexing
    
    whiteningMatrix = rez.Wrot/200;
    whiteningMatrixInv = whiteningMatrix^-1;
    writeNPY(whiteningMatrix, fullfile(savePath, 'whitening_mat.npy'));
    writeNPY(whiteningMatrixInv, fullfile(savePath, 'whitening_mat_inv.npy'));
    
    if isfield(rez, 'simScore')
        similarTemplates = rez.simScore;
        writeNPY(similarTemplates, fullfile(savePath, 'similar_templates.npy'));
    end
    
     %make params file
    if ~exist(fullfile(savePath,'params.py'),'file')
        fid = fopen(fullfile(savePath,'params.py'), 'w');
        
        [~, fname, ext] = fileparts(rez.ops.fbinary);
        
        fprintf(fid,['dat_path = ''',fname ext '''\n']);
        fprintf(fid,'n_channels_dat = %i\n',rez.ops.NchanTOT);
        fprintf(fid,'dtype = ''int16''\n');
        fprintf(fid,'offset = 0\n');
        if mod(rez.ops.fs,1)
            fprintf(fid,'sample_rate = %i\n',rez.ops.fs);
        else
            fprintf(fid,'sample_rate = %i.\n',rez.ops.fs);
        end
        fprintf(fid,'hp_filtered = False');
        fclose(fid);
    end
end
