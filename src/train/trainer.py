from src.models.io_model import save_checkpoint
from tqdm import tqdm
from src.metrics.training_metrics import AverageMeter
from src.logging_conf import logger



class TrainerArgs:
    def __init__(self, n_epochs=50, device="cpu", output_path=""):
        self.n_epochs = n_epochs
        self.device = device
        self.output_path = output_path

class Trainer:

    def __init__(self, args, model, optimizer, criterion, start_epoch, train_loader, val_loader, lr_scheduler, writer):
        self.model = model
        self.optimizer = optimizer
        self.criterion = criterion

        self.train_data_loader = train_loader
        self.number_train_data = len(self.train_data_loader)

        self.valid_data_loader = val_loader
        self.number_val_data = len(self.valid_data_loader)

        self.lr_scheduler = lr_scheduler
        self.writer = writer

        self.start_epoch = start_epoch
        self.args = args

    def start(self):
        best_loss = 1000

        for epoch in range(self.start_epoch, self.args.n_epochs):
            train_dice_loss, train_dice_score = self.train_epoch(epoch)
            val_dice_loss, val_dice_score = self.val_epoch(epoch)

            if self.lr_scheduler:
                self.lr_scheduler.step(val_dice_loss)

            self._epoch_summary(epoch, train_dice_loss, val_dice_loss, train_dice_score, val_dice_score)
            is_best = bool(val_dice_loss < best_loss)
            best_loss = val_dice_loss if is_best else best_loss

            save_checkpoint({
                'epoch': epoch + 1,
                'model_state_dict': self.model.state_dict(),
                'optimizer_state_dict': self.optimizer.state_dict(),
                'val_loss': best_loss,
                'val_dice_score': val_dice_score
            }, is_best, self.args.output_path)


    def train_epoch(self, epoch):
        self.model.train()
        losses = AverageMeter()
        dice_score = AverageMeter()

        i = 0
        for data_batch, labels_batch in tqdm(self.train_data_loader, desc="Training epoch"):
            def step(trainer):
                trainer.optimizer.zero_grad()

                inputs = data_batch.float().to(trainer.args.device)
                targets = labels_batch.float().to(trainer.args.device)
                inputs.require_grad = True

                predictions, _ = trainer.model(inputs)
                loss_dice, mean_dice = trainer.criterion(predictions, targets)
                loss_dice.backward()
                trainer.optimizer.step()

                loss_dice = loss_dice.detach().item()
                mean_dice = mean_dice.detach().item()
                losses.update(loss_dice, data_batch.size(0))
                dice_score.update(mean_dice, data_batch.size(0))

                trainer.writer.add_scalar('Training Dice Loss', loss_dice, epoch * trainer.number_train_data + i)
                trainer.writer.add_scalar('Training Dice Score', mean_dice, epoch * trainer.number_train_data + i)

            step(self)


            i += 1

        return losses.avg(), dice_score.avg()

    def val_epoch(self, epoch):
        self.model.eval()
        losses = AverageMeter()
        dice_score = AverageMeter()

        i = 0
        for data_batch, labels_batch in tqdm(self.valid_data_loader, desc="Validation epoch"):
            def step(trainer):
                inputs = data_batch.float().to(trainer.args.device)
                targets = labels_batch.float().to(trainer.args.device)
                inputs.require_grad = False

                outputs, _ = trainer.model(inputs)

                loss_dice, mean_dice = trainer.criterion(outputs, targets)

                loss_dice.backward()
                loss_dice = loss_dice.detach().item()
                mean_dice = mean_dice.detach().item()

                losses.update(loss_dice, data_batch.size(0))
                dice_score.update(mean_dice, data_batch.size(0))
                trainer.writer.add_scalar('Validation Dice Loss', loss_dice, epoch * trainer.number_val_data + i)
                trainer.writer.add_scalar('Validation Dice Score', mean_dice, epoch * trainer.number_val_data + i)

            step(self)

            i += 1

        return losses.avg(), dice_score.avg()

    def _epoch_summary(self, epoch, train_loss, val_loss, train_dice_score, val_dice_score):
        logger.info(f'epoch: {epoch}\n '
                    f'**Dice Loss: train_loss: {train_loss:.2f} | val_loss {val_loss:.2f} \n'
                    f'**Dice Score: train_dice_score {train_dice_score:.2f} | val_dice_score {val_dice_score:.2f}')

