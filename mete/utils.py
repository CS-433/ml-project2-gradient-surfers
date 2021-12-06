import numpy as np
import matplotlib.pyplot as plt
from numpy.random.mtrand import normal
import seaborn as sns
from scipy.signal import find_peaks_cwt
import torch
from torch.utils.data import Dataset, DataLoader, random_split
from tqdm import tqdm

def find_extrema(event, extrema_th=2):
    extrema = []
    extrema.append(event[0])

    for i in range(1, len(event)-1):
        this_current = event[i, 1]
        prev_current = event[i-1, 1]
        next_current = event[i+1, 1]
        prev_change = this_current - prev_current
        next_change = this_current - next_current
        if prev_change * next_change >= 0:
            extrema_change = np.abs(this_current - extrema[-1][1])
            if extrema_change > extrema_th:
                extrema.append(event[i])
    
    extrema.append(event[-1])

    return np.array(extrema)

def find_current_diffs(event):
    current_diffs = []

    for i in range(1, len(event)):
        current_diffs.append(event[i, 1] - event[i-1, 1])
    
    return np.array(current_diffs)

def plot_data(data, plot_extrema=False, extrema_th=2):
    k = len(data)
    fig, axes = plt.subplots(k, 1, figsize=(30, 15), sharex=True, sharey=True)

    for i in range(k):
        event = data[i]
        time = event[:, 0]
        current = event[:, 1]

        g = sns.lineplot(x=time, y=current, ax=axes[i])
        g.set_xlabel('Time [ms]')
        g.set_ylabel('Current')

        if plot_extrema:
            # extrema = find_extrema(event, extrema_th=extrema_th)
            peaks_idx = find_peaks_cwt(event[:, 1], widths=event[-1][0])
            peaks = event[peaks_idx]
            time = peaks[:, 0]
            current = peaks[:, 1]
            g = sns.scatterplot(x=time, y=current, ax=axes[i], s=100, color='blue')

def build_features(event, extrema_th=0):
    features = {
        'num_signals': 0, 
        'duration': 0,
        'max_current': 0, 
        'min_current': 0, 
        'mean_current': 0,
        'std_current': 0,
        'num_extrema': 0, 
        'mean_extrema': 0,
        'std_extrema': 0,
        'mean_extrema_diff': 0,
        'num_peaks': 0,
        'mean_peaks': 0,
        'peak_1': 0,
        'peak_2': 0,
        'peak_3': 0,
        'peak_4': 0,
        'peak_5': 0
    }
    if len(event) > 0:
        features['num_signals'] = len(event)
        features['duration'] = event[-1][0]
        features['max_current'] = np.max(event[:, 1])
        features['min_current'] = np.min(event[:, 1])
        features['mean_current'] = np.mean(event[:, 1])
        features['std_current'] = np.std(event[:, 1])
        extrema = find_extrema(event, extrema_th=extrema_th)
        features['num_extrema'] = len(extrema)
        features['mean_extrema'] = np.mean(extrema)
        features['std_extrema'] = np.std(extrema)
        features['mean_extrema_diff'] = np.mean(np.abs([extrema[i, 1] - extrema[i-1, 1] for i in range(1, len(extrema))]))
        peaks_idx = find_peaks_cwt(event[:, 1], widths=max([1, event[-1][0]]))
        features['num_peaks'] = len(peaks_idx)
        if len(peaks_idx) > 0:
            peaks = sorted(event[peaks_idx][:, 1], reverse=True)
            features['mean_peaks'] = np.mean(peaks)
            features['peak_1'] = peaks[0] if len(peaks) > 0 else 0
            features['peak_2'] = peaks[1] if len(peaks) > 1 else 0
            features['peak_3'] = peaks[2] if len(peaks) > 2 else 0
            features['peak_4'] = peaks[3] if len(peaks) > 3 else 0
            features['peak_5'] = peaks[4] if len(peaks) > 4 else 0
    return features

class PolymerDataset(Dataset):
    def __init__(self, data_paths, timesteps=None, stepsize=None, extrema_th=0, save_path=None) -> None:
        self.data_paths = data_paths
        self.raw_data = [np.load(data_path, allow_pickle=True) for data_path in data_paths]
        self.preprocess(timesteps=timesteps, stepsize=stepsize, extrema_th=extrema_th)
        if save_path:
            torch.save(self.data, save_path)
    
    def __len__(self):
        return len(self.labels)
    
    def __getitem__(self, idx):
        return self.data[idx], self.labels[idx]
    
    @property
    def num_features(self):
        return self.data.shape[2]
    
    @property
    def num_classes(self):
        return len(torch.unique(self.labels))

    def _process_event(self, event, timesteps, stepsize=None, extrema_th=0):
        compressed_event = []
        stepsize = stepsize or int(np.ceil(len(event) / timesteps))
        for i in range(timesteps):
            sub_event = event[i*stepsize:(i+1)*stepsize]
            features = build_features(sub_event, extrema_th=extrema_th)
            compressed_event.append(np.array(list(features.values())))
        return np.array(compressed_event)

    def preprocess(self, timesteps=None, stepsize=None, extrema_th=0, seed=42):
        data = []
        labels = []

        if not timesteps and not stepsize:
            raise ValueError('Either timesteps or stepsize should be specified')

        np.random.seed(seed)

        # Make data balanced
        balanced_data = []
        min_data_size = min([len(d) for d in self.raw_data])
        for r_data in self.raw_data:
            indices = np.random.permutation(len(r_data))
            balanced_data.append(r_data[indices[:min_data_size]])

        # Remove too short and too long events
        normal_data = []
        for b_data in balanced_data:
            event_lens = [len(event) for event in b_data]
            # min_event_len = np.quantile(event_lens, 0.1)
            min_event_len = 50
            # max_event_len = np.quantile(event_lens, 0.9)
            max_event_len = 10000
            normal_events = []
            for event in b_data:
                if len(event) > min_event_len and len(event) < max_event_len:
                    normal_events.append(event)
            normal_data.append(normal_events)

        # Calculate timesteps
        max_event_len = np.max([len(event) for n_data in normal_data for event in n_data])
        timesteps = timesteps or int(np.ceil(max_event_len / stepsize))

        # Preprocess events
        for data_index, raw_data in enumerate(normal_data):
            for event in tqdm(raw_data, desc=f'Processing {self.data_paths[data_index]}'):
                processed_event = self._process_event(event, timesteps=timesteps, stepsize=stepsize, extrema_th=extrema_th)
                data.append(processed_event)
                labels.append(data_index)

        self.data = torch.tensor(np.array(data), dtype=torch.float)
        self.labels = torch.tensor(np.array(labels), dtype=torch.long)
        return self

class PolymerLSTM(torch.nn.Module):
    def __init__(self, num_features, num_classes, num_layers=1, hidden_size=32) -> None:
        super().__init__()
        self.lstm = torch.nn.LSTM(input_size=num_features, num_layers=num_layers, hidden_size=hidden_size, batch_first=True)
        self.linear = torch.nn.Linear(hidden_size, num_classes)
    
    def forward(self, X):
        lstm_out, _ = self.lstm(X)
        outputs = lstm_out[:, -1, :]
        outputs = self.linear(outputs)
        probs = torch.nn.functional.log_softmax(outputs, dim=1)
        return probs
    
    def predict(self, X):
        probs = self.forward(X)
        preds = torch.argmax(probs, dim=1, keepdim=False)
        return preds


def train(dataset, num_epochs=100, batch_size=64, num_features=2, num_classes=2, hidden_size=32, num_layers=1, lr_rate=0.05):
    data_loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    model = PolymerLSTM(num_features, num_classes, num_layers=num_layers, hidden_size=hidden_size)
    loss_function = torch.nn.NLLLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr_rate)

    for epoch in range(num_epochs):
        num_correct = 0
        for X, y in iter(data_loader):
            model.zero_grad()
            probs = model(X)
            loss = loss_function(probs, y)
            loss.backward()
            optimizer.step()
            preds = torch.argmax(probs, dim=1, keepdim=False)
            num_correct += (preds == y).sum()
        print(f'epoch={epoch}/{num_epochs}, loss={loss}, accuracy={num_correct*100/len(dataset)}')
    
    return model

def train_test_split(dataset, test_size=0.2):
    test_size = int(test_size * len(dataset))
    train_size = len(dataset) - test_size
    train_data, test_data = random_split(dataset, [train_size, test_size])
    return train_data, test_data